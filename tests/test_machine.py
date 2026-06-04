import pytest
import os
import json
import tempfile
from translator import main as translate
from machine import main as simulate, Machine
from isa import OPCODE_TO_CODE, Opcode


def _run(source_code: str, trap_schedule: list) -> str:
    """Translate source, simulate, return stdout string."""
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

        REV = {v: k for k, v in OPCODE_TO_CODE.items()}
        instrs = []
        for i in range(0, len(data), 4):
            b = data[i : i + 4]
            imm = (b[2] << 8) | b[3]
            if b[2] >= 128:
                imm -= 65536
            instrs.append(
                {"opcode": REV[b[0]], "rd": b[1] >> 4, "rs1": b[1] & 0xF, "imm": imm}
            )

        m = Machine(instrs, mem, trap_schedule=trap_schedule)
        while not m.halted and m.ticks < 15000:
            m.step()

        instr_count = len(instrs)
        result = " ".join(m.out)
        return (
            f"--- SUCCESS: {instr_count} instrs ---\n\n"
            f"--- SIMULATION FINISHED ---\n"
            f"Result: {result}\n"
            f"Ticks: {m.ticks}\n"
            f"Cache Hits: {m.cache.hits}, Misses: {m.cache.misses}"
        )


@pytest.mark.golden_test("../golden/*.yml")
def test_everything(golden):
    source = golden["in_source"]
    schedule_raw = golden.get("in_trap_schedule", "[]")
    trap_schedule = json.loads(schedule_raw) if isinstance(schedule_raw, str) else schedule_raw

    result = _run(source, trap_schedule)
    assert result == golden.out["out_stdout"]