import sys
import logging
import json
from isa import Opcode, OPCODE_TO_CODE

logging.basicConfig(level=logging.DEBUG, stream=sys.stdout, format="%(message)s")


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
        self.cache = Cache()
        self.out = []
        self.stack = []
        self.traps = sorted(trap_schedule or [], key=lambda x: x[0])
        self.zf = False
        self.gf = False
        self.in_isr = False
        self.pc_saved = 0
        self.trap_val = 0

    def step(self):
        if self.pc >= len(self.instrs):
            self.halted = True
            return
        if not self.in_isr and self.traps and self.ticks >= self.traps[0][0]:
            t, v = self.traps.pop(0)
            self.pc_saved = self.pc
            self.trap_val = v
            self.in_isr = True
            self.pc = 0
            logging.debug(f"TICK: {self.ticks:04} | !!! TRAP INTERRUPT: Value {v} !!!")
            self.ticks += 5
            return

        i = self.instrs[self.pc]
        op, rd, rs1, imm = i['opcode'], i['rd'], i['rs1'], i['imm']
        logging.debug(f"Tick: {self.ticks:04} | PC: {self.pc:02} {op:4} R1:{self.regs[1]} R2:{self.regs[2]}")
        self.ticks += 1

        if op == Opcode.LI:
            self.regs[rd] = imm
            self.pc += 1
        elif op == Opcode.LW:
            addr = self.regs[rs1] + imm
            if not self.cache.check(addr):
                self.ticks += 10
            self.regs[rd] = self.mem[addr]
            self.pc += 1
        elif op == Opcode.SW:
            addr = self.regs[rd] + imm
            if not self.cache.check(addr):
                self.ticks += 10
            self.mem[addr] = self.regs[rs1]
            self.pc += 1
        elif op == Opcode.ADD:
            self.regs[rd] = self.regs[rs1] + self.regs[imm]
            self.pc += 1
        elif op == Opcode.MUL:
            self.regs[rd] = self.regs[rs1] * self.regs[imm]
            self.pc += 1
        elif op == Opcode.SUB:
            self.regs[rd] = self.regs[rs1] - self.regs[imm]
            self.pc += 1
        elif op == Opcode.CMP:
            self.zf = (self.regs[rs1] == self.regs[imm])
            self.gf = (self.regs[rs1] > self.regs[imm])
            self.pc += 1
        elif op == Opcode.BGT:
            self.pc = imm if self.gf else self.pc + 1
        elif op == Opcode.BEQ:
            self.pc = imm if self.zf else self.pc + 1
        elif op == Opcode.BNE:
            self.pc = imm if not self.zf else self.pc + 1
        elif op == Opcode.JMP:
            self.pc = imm
        elif op == Opcode.IN:
            self.regs[rd] = self.trap_val
            self.pc += 1
        elif op == Opcode.OUT:
            val = self.regs[rs1]
            if imm == 0x85:
                l = self.mem[val]
                self.out.append("".join(chr(self.mem[val + 1 + j]) for j in range(l)))
            else:
                self.out.append(str(val))
            self.pc += 1
        elif op == Opcode.IRET:
            self.pc = self.pc_saved
            self.in_isr = False
            self.pc += 1
        elif op == Opcode.HALT:
            self.halted = True


def main(bin_f):
    with open(bin_f, "rb") as f:
        data = f.read()
    with open(bin_f + ".mem", "r") as f:
        mem = json.load(f)
    instrs = []
    REV = {v: k for k, v in OPCODE_TO_CODE.items()}
    for i in range(0, len(data), 4):
        b = data[i:i + 4]
        imm = (b[2] << 8) | b[3]
        if b[2] >= 128:
            imm -= 65536
        instrs.append({'opcode': REV[b[0]], 'rd': b[1] >> 4, 'rs1': b[1] & 0xF, 'imm': imm})
    m = Machine(instrs, mem)
    while not m.halted and m.ticks < 15000:
        m.step()
    print(f"\n--- SIMULATION FINISHED ---\nResult: {' '.join(m.out)}\nTicks: {m.ticks}")


if __name__ == "__main__":
    main(sys.argv[1])