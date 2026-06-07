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
        self.zf = False
        self.gf = False
        self.in_isr = False
        self.trap_val = 0
        self.traps = sorted(trap_schedule or [], key=lambda x: x[0])

    def _check_trap(self):
        if not self.in_isr and self.traps and self.ticks >= self.traps[0][0]:
            t, v = self.traps.pop(0)
            self.trap_val = v
            self.in_isr = True
            logging.debug(f"TICK: {self.ticks:04} | !!! TRAP INTERRUPT: Value {v} !!!")
            self.ticks += 5
            return True
        return False

    def step(self):
        if self.pc >= len(self.instrs):
            self.halted = True
            return
        self._check_trap()
        instr = self.instrs[self.pc]
        op, rd, rs1, imm = instr['opcode'], instr['rd'], instr['rs1'], instr['imm']
        logging.debug(
            f"Tick: {self.ticks:04} | PC: {self.pc:02} {op.value:7} "
            f"R1:{self.regs[1]} R2:{self.regs[2]} | G:{int(self.gf)} Z:{int(self.zf)}"
        )
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
            self.pc = imm if not self.gf else self.pc + 1
        elif op == Opcode.BNE:
            self.pc = imm if not self.zf else self.pc + 1
        elif op == Opcode.JMP:
            self.pc = imm
        elif op == Opcode.IN:
            while not self.in_isr and self.traps:
                self.ticks += 1
                if self._check_trap():
                    break
            self.regs[rd] = self.trap_val
            self.in_isr = False
            self.pc += 1
        elif op == Opcode.OUT:
            val = self.regs[rs1]
            if imm == 0x85:
                length = self.mem[val]
                self.out.append("".join(chr(self.mem[val + 1 + j]) for j in range(length)))
            elif imm == 0x86:
                self.out.append(chr(val))
            else:
                self.out.append(str(val))
            self.pc += 1
        elif op == Opcode.HALT:
            self.halted = True


def main(bin_f, trap_schedule=None):
    with open(bin_f, "rb") as f:
        data = f.read()
    with open(bin_f + ".mem", "r") as f:
        mem = json.load(f)
    instrs = []
    rev_code = {v: k for k, v in OPCODE_TO_CODE.items()}
    for i in range(0, len(data), 4):
        b = data[i:i + 4]
        imm = (b[2] << 8) | b[3]
        if b[2] >= 128:
            imm -= 65536
        instrs.append({
            'opcode': rev_code[b[0]],
            'rd': b[1] >> 4,
            'rs1': b[1] & 0xF,
            'imm': imm
        })
    m = Machine(instrs, mem, trap_schedule)
    while not m.halted and m.ticks < 15000:
        m.step()
    print(f"\n--- FINISHED ---\nResult: {' '.join(m.out)}")
    print(f"Ticks: {m.ticks}\nCache Hit: {m.cache.hits}")