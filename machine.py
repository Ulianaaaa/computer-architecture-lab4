import sys
import logging
import json
from isa import Opcode, OPCODE_TO_CODE

logging.basicConfig(level=logging.DEBUG, format="%(message)s")


class Cache:
    def __init__(self, size=4):
        self.size = size
        self.tags = [-1] * size
        self.hits = 0
        self.misses = 0

    def check(self, addr):
        if addr in self.tags:
            self.hits += 1
            return True
        self.misses += 1
        self.tags.pop(0)
        self.tags.append(addr)
        return False


class Machine:
    def __init__(self, instrs, mem, trap_schedule=None):
        self.instrs = instrs
        self.mem = mem
        self.regs = [0] * 16
        self.pc = 0
        self.ticks = 0
        self.halted = False
        self.gf = False
        self.cache = Cache()
        self.out = []
        self.trap_schedule = sorted(trap_schedule or [], key=lambda x: x[0])
        self.trap_port_value = 0
        self.in_isr = False
        self.pc_saved = 0
        self.isr_addr = None

    def _check_trap(self):
        if self.in_isr:
            return
        for i, (tick, value) in enumerate(self.trap_schedule):
            if self.ticks >= tick:
                logging.debug(
                    f"[TRAP] tick={self.ticks}: interrupt fired, port_value={value}, saving PC={self.pc + 1}"
                )
                self.trap_port_value = value
                self.trap_schedule.pop(i)
                self.pc_saved = self.pc + 1
                self.in_isr = True
                if self.isr_addr is not None:
                    self.pc = self.isr_addr
                self.ticks += 5
                return

    def step(self):
        if self.pc >= len(self.instrs):
            self.halted = True
            return

        self._check_trap()

        instr = self.instrs[self.pc]
        op, rd, rs1, imm = instr["opcode"], instr["rd"], instr["rs1"], instr["imm"]
        self.ticks += 1

        logging.debug(
            f"[tick={self.ticks:4d}] pc={self.pc:3d} | {op.value:4s} rd={rd} rs1={rs1} imm={imm:6d} "
            f"| regs={self.regs[:8]}"
        )

        if op == Opcode.LI:
            if rd != 0:
                self.regs[rd] = imm
            self.pc += 1

        elif op == Opcode.LW:
            addr = self.regs[rs1] + imm
            if not self.cache.check(addr):
                logging.debug(f"  [CACHE MISS] addr={addr}, +10 ticks")
                self.ticks += 10
            if rd != 0:
                self.regs[rd] = self.mem[addr]
            self.pc += 1

        elif op == Opcode.SW:
            addr = self.regs[rd] + imm
            if not self.cache.check(addr):
                logging.debug(f"  [CACHE MISS] addr={addr}, +10 ticks")
                self.ticks += 10
            self.mem[addr] = self.regs[rs1]
            self.pc += 1

        elif op == Opcode.ADD:
            if rd != 0:
                self.regs[rd] = self.regs[rs1] + self.regs[imm]
            self.pc += 1

        elif op == Opcode.SUB:
            if rd != 0:
                self.regs[rd] = self.regs[rs1] - self.regs[imm]
            self.pc += 1

        elif op == Opcode.MUL:
            if rd != 0:
                self.regs[rd] = self.regs[rs1] * self.regs[imm]
            self.pc += 1

        elif op == Opcode.DIV:
            if self.regs[imm] == 0:
                logging.debug("  [DIV] division by zero, result=0")
                if rd != 0:
                    self.regs[rd] = 0
            else:
                if rd != 0:
                    self.regs[rd] = self.regs[rs1] // self.regs[imm]
            self.pc += 1

        elif op == Opcode.CMP:
            self.gf = self.regs[rs1] > self.regs[imm]
            self.pc += 1

        elif op == Opcode.BGT:
            self.pc = imm if self.gf else self.pc + 1

        elif op == Opcode.BEQ:
            self.pc = imm if not self.gf else self.pc + 1

        elif op == Opcode.BNE:
            self.pc = imm if not self.gf else self.pc + 1

        elif op == Opcode.JMP:
            self.pc = imm

        elif op == Opcode.IN:
            if rd != 0:
                self.regs[rd] = self.trap_port_value
            logging.debug(f"  [IN] port=0x{imm:02x}, value={self.trap_port_value} -> r{rd}")
            self.pc += 1

        elif op == Opcode.OUT:
            val = self.regs[rs1]
            if imm == 0x85:
                length = self.mem[val]
                s = "".join(chr(self.mem[val + 1 + j]) for j in range(length))
                logging.debug(f"  [OUT] string={s!r}")
                self.out.append(s)
            else:
                logging.debug(f"  [OUT] number={val}")
                self.out.append(str(val))
            self.pc += 1

        elif op == Opcode.IRET:
            logging.debug(f"  [IRET] returning to pc={self.pc_saved}, in_isr=False")
            self.pc = self.pc_saved
            self.in_isr = False

        elif op == Opcode.HALT:
            self.halted = True


def main(bin_f, trap_schedule=None):
    with open(bin_f, "rb") as f:
        data = f.read()
    with open(bin_f + ".mem", "r") as f:
        mem = json.load(f)

    REV = {v: k for k, v in OPCODE_TO_CODE.items()}
    instrs = []
    for i in range(0, len(data), 4):
        b = data[i : i + 4]
        imm_raw = (b[2] << 8) | b[3]
        imm = imm_raw if b[2] < 128 else imm_raw - 65536
        instrs.append(
            {
                "opcode": REV[b[0]],
                "rd": b[1] >> 4,
                "rs1": b[1] & 0xF,
                "imm": imm,
            }
        )

    m = Machine(instrs, mem, trap_schedule=trap_schedule or [])
    while not m.halted and m.ticks < 15000:
        m.step()

    print(
        f"\n--- SIMULATION FINISHED ---\n"
        f"Result: {' '.join(m.out)}\n"
        f"Ticks: {m.ticks}\n"
        f"Cache Hits: {m.cache.hits}, Misses: {m.cache.misses}"
    )


if __name__ == "__main__":
    main(sys.argv[1])