import sys
import re
import json
from isa import Opcode, OPCODE_TO_CODE

TOKEN_TYPES = [
    ('STRING', r'"[^"]*"'), ('CONST', r'const'), ('FOR', r'for'), ('WHILE', r'while'),
    ('IF', r'if'), ('ELSE', r'else'), ('PRINT', r'print'), ('PUTCHAR', r'putchar'),
    ('READ', r'read'), ('NUMBER', r'\d+'), ('ID', r'[a-zA-Z_][a-zA-Z0-9_]*'),
    ('ASSIGN', r'='), ('OP', r'[+\-*/]'), ('CMP', r'[<>!=]=|[<>]'),
    ('LPAREN', r'\('), ('RPAREN', r'\)'), ('LBRACE', r'\{'), ('RBRACE', r'\}'),
    ('COMMA', r','), ('SEMICOLON', r';'), ('SKIP', r'[ \t\n]+'),
]


class Node:
    def __init__(self, kind, value=None, left=None, right=None, children=None):
        self.kind = kind
        self.value = value
        self.left = left
        self.right = right
        self.children = children or []

    def __repr__(self, lvl=0):
        indent = "  " * lvl
        s = f"{indent}|-- {self.kind}" + (f": {self.value}" if self.value is not None else "") + "\n"
        if self.left:
            s += self.left.__repr__(lvl + 1)
        if self.right:
            s += self.right.__repr__(lvl + 1)
        for c in self.children:
            s += c.__repr__(lvl + 1)
        return s


class Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0

    def peek(self, off=0):
        if self.pos + off < len(self.tokens):
            return self.tokens[self.pos + off]
        return ('EOF', '')

    def consume(self, k):
        kind, val = self.peek()
        if kind == k:
            self.pos += 1
            return val
        raise RuntimeError(f"Expected {k}, got {kind}")

    def parse_factor(self):
        k, v = self.peek()
        if k == 'NUMBER':
            return Node('NUMBER', value=int(self.consume('NUMBER')))
        if k == 'ID':
            return Node('VAR', value=self.consume('ID'))
        if k == 'STRING':
            return Node('STRING', value=self.consume('STRING')[1:-1])
        if k == 'READ':
            self.consume('READ')
            self.consume('LPAREN')
            self.consume('RPAREN')
            return Node('READ')
        if k == 'LPAREN':
            self.consume('LPAREN')
            expr = self.parse_expr()
            self.consume('RPAREN')
            return expr
        return None

    def parse_term(self):
        n = self.parse_factor()
        while self.peek()[0] == 'OP' and self.peek()[1] in '*/':
            op_val = self.consume('OP')
            n = Node('BIN_OP', value=op_val, left=n, right=self.parse_factor())
        return n

    def parse_expr(self):
        n = self.parse_term()
        while self.peek()[0] == 'OP' and self.peek()[1] in '+-':
            op_val = self.consume('OP')
            n = Node('BIN_OP', value=op_val, left=n, right=self.parse_term())
        return n

    def parse_stmt(self):
        k, v = self.peek()
        if k == 'CONST':
            self.consume('CONST')
        if k == 'ID':
            name = self.consume('ID')
            self.consume('ASSIGN')
            expr = self.parse_expr()
            self.consume('SEMICOLON')
            return Node('ASSIGN', value=name, left=expr)
        if k == 'IF':
            self.consume('IF')
            self.consume('LPAREN')
            l_val = self.parse_expr()
            op = self.consume('CMP')
            r_val = self.parse_expr()
            self.consume('RPAREN')
            self.consume('LBRACE')
            body = []
            while self.peek()[0] != 'RBRACE':
                body.append(self.parse_stmt())
            self.consume('RBRACE')
            else_b = []
            if self.peek()[0] == 'ELSE':
                self.consume('ELSE')
                self.consume('LBRACE')
                while self.peek()[0] != 'RBRACE':
                    else_b.append(self.parse_stmt())
                self.consume('RBRACE')
            return Node('IF', value=op, children=[l_val, r_val, Node('BODY', children=body), Node('ELSE', children=else_b)])
        if k == 'FOR':
            self.consume('FOR')
            self.consume('LPAREN')
            v_n = self.consume('ID')
            self.consume('ASSIGN')
            start = self.parse_expr()
            self.consume('COMMA')
            end = self.parse_expr()
            self.consume('COMMA')
            step = self.parse_expr()
            self.consume('RPAREN')
            self.consume('LBRACE')
            body = []
            while self.peek()[0] != 'RBRACE':
                body.append(self.parse_stmt())
            self.consume('RBRACE')
            return Node('FOR', value=v_n, children=[start, end, step] + body)
        if k == 'PRINT':
            self.consume('PRINT')
            self.consume('LPAREN')
            expr = self.parse_expr()
            self.consume('RPAREN')
            self.consume('SEMICOLON')
            return Node('PRINT', left=expr)
        if k == 'PUTCHAR':
            self.consume('PUTCHAR')
            self.consume('LPAREN')
            expr = self.parse_expr()
            self.consume('RPAREN')
            self.consume('SEMICOLON')
            return Node('PUTCHAR', left=expr)
        self.pos += 1
        return None

    def parse_prog(self):
        nodes = []
        while self.peek()[0] != 'EOF':
            n = self.parse_stmt()
            if n:
                nodes.append(n)
        return nodes


class CodeGen:
    def __init__(self):
        self.instrs = []
        self.vars = {}
        self.mem = [0] * 1024
        self.next_addr = 100
        self.regs = 0
        self.string_vars = set()

    def get_addr(self, name, size=1):
        if name not in self.vars:
            self.vars[name] = self.next_addr
            self.next_addr += size
        return self.vars[name]

    def emit(self, op, rd=0, rs1=0, imm=0):
        self.instrs.append({'opcode': op, 'rd': rd, 'rs1': rs1, 'imm': imm})
        return len(self.instrs) - 1

    def gen_expr(self, n):
        if n.kind == 'NUMBER':
            r = self.regs + 1
            self.regs += 1
            if n.value > 32767:
                addr = self.get_addr(f"c_{n.value}")
                self.mem[addr] = n.value
                self.emit(Opcode.LW, rd=r, rs1=0, imm=addr)
            else:
                self.emit(Opcode.LI, rd=r, imm=n.value)
            return r
        if n.kind == 'VAR':
            r = self.regs + 1
            self.regs += 1
            addr = self.get_addr(n.value)
            self.emit(Opcode.LW, rd=r, rs1=0, imm=addr)
            return r
        if n.kind == 'READ':
            r = self.regs + 1
            self.regs += 1
            self.emit(Opcode.IN, rd=r, imm=0x80)
            return r
        if n.kind == 'STRING':
            addr = self.get_addr(f"s_{n.value}", len(n.value) + 1)
            self.mem[addr] = len(n.value)
            for i, c in enumerate(n.value):
                self.mem[addr + 1 + i] = ord(c)
            r = self.regs + 1
            self.regs += 1
            self.emit(Opcode.LI, rd=r, imm=addr)
            return r
        if n.kind == 'BIN_OP':
            l_r = self.gen_expr(n.left)
            r_r = self.gen_expr(n.right)
            if n.value == '+':
                self.emit(Opcode.ADD, rd=l_r, rs1=l_r, imm=r_r)
            elif n.value == '-':
                self.emit(Opcode.SUB, rd=l_r, rs1=l_r, imm=r_r)
            elif n.value == '*':
                self.emit(Opcode.MUL, rd=l_r, rs1=l_r, imm=r_r)
            self.regs -= 1
            return l_r
        return 0

    def gen_stmt(self, n):
        if n.kind == 'ASSIGN':
            if n.left.kind == 'STRING':
                self.string_vars.add(n.value)
            r = self.gen_expr(n.left)
            addr = self.get_addr(n.value)
            self.emit(Opcode.SW, rs1=r, rd=0, imm=addr)
            self.regs = 0
        elif n.kind == 'PRINT':
            is_var_str = n.left.kind == 'VAR' and n.left.value in self.string_vars
            is_s = is_var_str or (n.left.kind == 'STRING')
            r = self.gen_expr(n.left)
            self.emit(Opcode.OUT, rs1=r, imm=0x85 if is_s else 0x84)
            self.regs = 0
        elif n.kind == 'PUTCHAR':
            r = self.gen_expr(n.left)
            self.emit(Opcode.OUT, rs1=r, imm=0x86)
            self.regs = 0
        elif n.kind == 'IF':
            r1 = self.gen_expr(n.children[0])
            r2 = self.gen_expr(n.children[1])
            self.emit(Opcode.CMP, rs1=r1, imm=r2)
            exit_if = self.emit(Opcode.BEQ, imm=0)
            self.regs = 0
            for s in n.children[2].children:
                self.gen_stmt(s)
            self.instrs[exit_if]['imm'] = len(self.instrs)
        elif n.kind == 'FOR':
            addr = self.get_addr(n.value)
            start_r = self.gen_expr(n.children[0])
            self.emit(Opcode.SW, rs1=start_r, rd=0, imm=addr)
            self.regs = 0
            start_l = len(self.instrs)
            r1 = self.gen_expr(Node('VAR', value=n.value))
            r2 = self.gen_expr(n.children[1])
            self.emit(Opcode.CMP, rs1=r1, imm=r2)
            exit_f = self.emit(Opcode.BGT, imm=0)
            self.regs = 0
            for i in range(3, len(n.children)):
                self.gen_stmt(n.children[i])
            r1 = self.gen_expr(Node('VAR', value=n.value))
            step_r = self.gen_expr(n.children[2])
            self.emit(Opcode.ADD, rd=r1, rs1=r1, imm=step_r)
            self.emit(Opcode.SW, rs1=r1, rd=0, imm=addr)
            self.regs = 0
            self.emit(Opcode.JMP, imm=start_l)
            self.instrs[exit_f]['imm'] = len(self.instrs)


def main(src_f, tgt_f):
    with open(src_f, "r") as f:
        code = f.read()
    tokens = []
    regex = '|'.join('(?P<%s>%s)' % pair for pair in TOKEN_TYPES)
    for mo in re.finditer(regex, code):
        if mo.lastgroup != 'SKIP':
            tokens.append((mo.lastgroup, mo.group()))
    ast = Parser(tokens).parse_prog()
    print("--- AST ---")
    for n in ast:
        print(n)
    gen = CodeGen()
    for n in ast:
        gen.gen_stmt(n)
    gen.emit(Opcode.HALT)
    res_bin = bytearray()
    for i in gen.instrs:
        res_bin.append(OPCODE_TO_CODE[i['opcode']])
        res_bin.append((i['rd'] << 4) | i['rs1'])
        res_bin.extend([(i['imm'] >> 8) & 0xFF, i['imm'] & 0xFF])
    with open(tgt_f, "wb") as f:
        f.write(res_bin)
    with open(tgt_f + ".mem", "w") as f:
        json.dump(gen.mem, f)
    print(f"--- SUCCESS: {len(gen.instrs)} instrs ---")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python translator.py <source> <target>")
    else:
        main(sys.argv[1], sys.argv[2])