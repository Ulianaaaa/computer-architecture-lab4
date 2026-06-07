from enum import Enum


class Opcode(str, Enum):
    ADD = "add"
    SUB = "sub"
    MUL = "mul"
    DIV = "div"
    LW = "lw"
    SW = "sw"
    LI = "li"
    CMP = "cmp"
    JMP = "jmp"
    BEQ = "beq"
    BNE = "bne"
    BGT = "bgt"
    IN = "in"
    OUT = "out"
    IRET = "iret"
    HALT = "halt"


OPCODE_TO_CODE = {
    Opcode.ADD: 0x01,
    Opcode.SUB: 0x02,
    Opcode.MUL: 0x03,
    Opcode.DIV: 0x04,
    Opcode.LW: 0x05,
    Opcode.SW: 0x06,
    Opcode.LI: 0x07,
    Opcode.CMP: 0x08,
    Opcode.JMP: 0x09,
    Opcode.BEQ: 0x0A,
    Opcode.BNE: 0x0B,
    Opcode.BGT: 0x0C,
    Opcode.IN: 0x0D,
    Opcode.OUT: 0x0E,
    Opcode.IRET: 0x10,
    Opcode.HALT: 0xFF
}