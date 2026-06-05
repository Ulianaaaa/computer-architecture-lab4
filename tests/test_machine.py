import pytest
import os
import json
import tempfile
import logging
import io
from translator import main as translate
from machine import Machine
from isa import OPCODE_TO_CODE


def _run_test(source_code, trap_schedule):
    with tempfile.TemporaryDirectory() as tmpdir:
        src = os.path.join(tmpdir, "source.alg")
        tgt = os.path.join(tmpdir, "target.bin")

        with open(src, "w", encoding="utf-8") as f:
            f.write(source_code)

        translate(src, tgt)

        with open(tgt, "rb") as f:
            data = f.read()
        with open(tgt + ".mem", "r") as f:
            mem = json.load(f)

        machine_code_log = "ADDRESS  - HEXCODE  - MNEMONIC\n"
        machine_code_log += "--------------------------------\n"
        REV = {v: k for k, v in OPCODE_TO_CODE.items()}
        instrs = []
        for i in range(0, len(data), 4):
            b = data[i:i + 4]
            imm = (b[2] << 8) | b[3]
            if b[2] >= 128:
                imm -= 65536
            opcode = REV[b[0]]
            instrs.append({"opcode": opcode, "rd": b[1] >> 4, "rs1": b[1] & 0xF, "imm": imm})
            machine_code_log += f"{i:08X} - {b.hex().upper()} - {opcode} rd:{b[1] >> 4} rs1:{b[1] & 0xF} imm:{imm}\n"

        log_stream = io.StringIO()
        logger = logging.getLogger()
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)
        logger.addHandler(logging.StreamHandler(log_stream))
        logger.setLevel(logging.DEBUG)

        m = Machine(instrs, mem, trap_schedule=trap_schedule)
        while not m.halted and m.ticks < 15000:
            m.step()

        return machine_code_log, log_stream.getvalue(), " ".join(m.out)


@pytest.mark.golden_test("../golden/*.yml")
def test_everything(golden):
    source = golden["in_source"]
    schedule_raw = golden.get("in_trap_schedule", "[]")
    schedule = json.loads(schedule_raw) if isinstance(schedule_raw, str) else schedule_raw

    code, log, stdout = _run_test(source, schedule)

    assert code.strip() == golden.out["out_code"]
    assert log.strip() == golden.out["out_log"]
    assert stdout.strip() == golden.out["out_stdout"]