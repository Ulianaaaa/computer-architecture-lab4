import sys, re, json
from isa import Opcode, OPCODE_TO_CODE

TOKEN_TYPES = [
    ('STRING',   r'"[^"]*"'), ('CONST',    r'const'), ('FOR',      r'for'), ('WHILE',    r'while'),
    ('IF',       r'if'), ('ELSE',     r'else'), ('PRINT',    r'print'), ('READ',     r'read'),
    ('NUMBER',   r'\d+'), ('ID',       r'[a-zA-Z_][a-zA-Z0-9_]*'), ('ASSIGN',   r'='),
    ('OP',       r'[+\-*/]'), ('CMP',      r'[<>!=]=|[<>]'), ('LPAREN',   r'\('), ('RPAREN',   r'\)'),
    ('LBRACE',   r'\{'), ('RBRACE',   r'\}'), ('COMMA',    r','), ('SEMICOLON',r';'), ('SKIP',     r'[ \t\n]+'),
]

class Node:
    def __init__(self, kind, value=None, left=None, right=None, children=None):
        self.kind, self.value, self.left, self.right, self.children = kind, value, left, right, children or []
    def __repr__(self, lvl=0):
        s = "  " * lvl + f"|-- {self.kind}" + (f": {self.value}" if self.value is not None else "") + "\n"
        if self.left: s += self.left.__repr__(lvl + 1)
        if self.right: s += self.right.__repr__(lvl + 1)
        for c in self.children: s += c.__repr__(lvl + 1)
        return s

class Parser:
    def __init__(self, tokens): self.tokens, self.pos = tokens, 0
    def peek(self, off=0): return self.tokens[self.pos+off] if self.pos+off < len(self.tokens) else ('EOF', '')
    def consume(self, k):
        kind, val = self.peek()
        if kind == k: self.pos += 1; return val
        raise RuntimeError(f"Expected {k}, got {kind}")
    def parse_factor(self):
        k, v = self.peek()
        if k == 'NUMBER': return Node('NUMBER', value=int(self.consume('NUMBER')))
        if k == 'ID': return Node('VAR', value=self.consume('ID'))
        if k == 'STRING': return Node('STRING', value=self.consume('STRING')[1:-1])
        if k == 'READ': self.consume('READ'); self.consume('LPAREN'); self.consume('RPAREN'); return Node('READ')
        if k == 'LPAREN': self.consume('LPAREN'); n = self.parse_expr(); self.consume('RPAREN'); return n
    def parse_term(self):
        n = self.parse_factor()
        while self.peek()[0] == 'OP' and self.peek()[1] in '*/':
            n = Node('BIN_OP', value=self.consume('OP'), left=n, right=self.parse_factor())
        return n
    def parse_expr(self):
        n = self.parse_term()
        while self.peek()[0] == 'OP' and self.peek()[1] in '+-':
            n = Node('BIN_OP', value=self.consume('OP'), left=n, right=self.parse_term())
        return n
    def parse_stmt(self):
        k, v = self.peek()
        if k == 'CONST': self.consume('CONST')
        if k == 'ID':
            name = self.consume('ID'); self.consume('ASSIGN'); expr = self.parse_expr(); self.consume('SEMICOLON')
            return Node('ASSIGN', value=name, left=expr)
        if k == 'IF':
            self.consume('IF'); self.consume('LPAREN'); l = self.parse_expr(); op = self.consume('CMP'); r = self.parse_expr(); self.consume('RPAREN'); self.consume('LBRACE')
            body = []
            while self.peek()[0] != 'RBRACE': body.append(self.parse_stmt())
            self.consume('RBRACE')
            else_b = []
            if self.peek()[0] == 'ELSE':
                self.consume('ELSE'); self.consume('LBRACE')
                while self.peek()[0] != 'RBRACE': else_b.append(self.parse_stmt())
                self.consume('RBRACE')
            return Node('IF', value=op, children=[l, r, Node('BODY', children=body), Node('ELSE', children=else_b)])
        if k == 'WHILE':
            self.consume('WHILE'); self.consume('LPAREN'); l = self.parse_expr(); op = self.consume('CMP'); r = self.parse_expr(); self.consume('RPAREN'); self.consume('LBRACE')
            body = []
            while self.peek()[0] != 'RBRACE': body.append(self.parse_stmt())
            self.consume('RBRACE'); return Node('WHILE', value=op, children=[l, r] + body)
        if k == 'FOR':
            self.consume('FOR'); self.consume('LPAREN'); v_n = self.consume('ID'); self.consume('ASSIGN'); start = self.parse_expr(); self.consume('COMMA'); end = self.parse_expr(); self.consume('COMMA'); step = self.parse_expr(); self.consume('RPAREN'); self.consume('LBRACE')
            body = []
            while self.peek()[0] != 'RBRACE': body.append(self.parse_stmt())
            self.consume('RBRACE'); return Node('FOR', value=v_n, children=[start, end, step] + body)
        if k == 'PRINT':
            self.consume('PRINT'); self.consume('LPAREN'); expr = self.parse_expr(); self.consume('RPAREN'); self.consume('SEMICOLON')
            return Node('PRINT', left=expr)
        self.pos += 1
    def parse_prog(self):
        nodes = []
        while self.peek()[0] != 'EOF':
            n = self.parse_stmt()
            if n: nodes.append(n)
        return nodes

class CodeGen:
    def __init__(self): self.instrs, self.vars, self.mem, self.next_addr, self.regs, self.string_vars = [], {}, [0]*1024, 100, 0, set()
    def get_addr(self, name, size=1):
        if name not in self.vars: self.vars[name] = self.next_addr; self.next_addr += size
        return self.vars[name]
    def emit(self, op, rd=0, rs1=0, imm=0): self.instrs.append({'opcode': op, 'rd': rd, 'rs1': rs1, 'imm': imm}); return len(self.instrs)-1
    def gen_expr(self, n):
        if n.kind == 'NUMBER': r = self.regs + 1; self.regs += 1; self.emit(Opcode.LI, rd=r, imm=n.value); return r
        if n.kind == 'VAR': r = self.regs + 1; self.regs += 1; self.emit(Opcode.LW, rd=r, rs1=0, imm=self.get_addr(n.value)); return r
        if n.kind == 'READ': r = self.regs + 1; self.regs += 1; self.emit(Opcode.IN, rd=r, imm=0x80); return r
        if n.kind == 'STRING':
            addr = self.get_addr(f"s_{n.value}", len(n.value)+1); self.mem[addr] = len(n.value)
            for i, c in enumerate(n.value): self.mem[addr+1+i] = ord(c)
            r = self.regs + 1; self.regs += 1; self.emit(Opcode.LI, rd=r, imm=addr); return r
        if n.kind == 'BIN_OP':
            l = self.gen_expr(n.left); r_e = self.gen_expr(n.right)
            if n.value == '+': self.emit(Opcode.ADD, rd=l, rs1=l, imm=r_e)
            elif n.value == '-': self.emit(Opcode.SUB, rd=l, rs1=l, imm=r_e)
            elif n.value == '*': self.emit(Opcode.MUL, rd=l, rs1=l, imm=r_e)
            self.regs -= 1; return l
    def gen_stmt(self, n):
        if n.kind == 'ASSIGN':
            if n.left.kind == 'STRING': self.string_vars.add(n.value)
            r = self.gen_expr(n.left); self.emit(Opcode.SW, rs1=r, rd=0, imm=self.get_addr(n.value)); self.regs = 0
        elif n.kind == 'PRINT':
            is_s = (n.left.kind == 'VAR' and n.left.value in self.string_vars) or (n.left.kind == 'STRING')
            r = self.gen_expr(n.left); self.emit(Opcode.OUT, rs1=r, imm=0x85 if is_s else 0x84); self.regs = 0
        elif n.kind == 'IF':
            r1 = self.gen_expr(n.children[0]); r2 = self.gen_expr(n.children[1]); self.emit(Opcode.CMP, rs1=r1, imm=r2)
            exit_if = self.emit(Opcode.BEQ, imm=0); self.regs = 0
            for s in n.children[2].children: self.gen_stmt(s)
            if n.children[3].children:
                skip_else = self.emit(Opcode.JMP, imm=0); self.instrs[exit_if]['imm'] = len(self.instrs)
                for s in n.children[3].children: self.gen_stmt(s)
                self.instrs[skip_else]['imm'] = len(self.instrs)
            else: self.instrs[exit_if]['imm'] = len(self.instrs)
        elif n.kind == 'WHILE':
            start = len(self.instrs); r1 = self.gen_expr(n.children[0]); r2 = self.gen_expr(n.children[1])
            self.emit(Opcode.CMP, rs1=r1, imm=r2); exit_w = self.emit(Opcode.BEQ, imm=0); self.regs = 0
            for i in range(2, len(n.children)): self.gen_stmt(n.children[i])
            self.emit(Opcode.JMP, imm=start); self.instrs[exit_w]['imm'] = len(self.instrs)
        elif n.kind == 'FOR':
            addr = self.get_addr(n.value); start_r = self.gen_expr(n.children[0]); self.emit(Opcode.SW, rs1=start_r, rd=0, imm=addr); self.regs = 0
            start_l = len(self.instrs); r1 = self.gen_expr(Node('VAR', value=n.value)); r2 = self.gen_expr(n.children[1])
            self.emit(Opcode.CMP, rs1=r1, imm=r2); exit_f = self.emit(Opcode.BGT, imm=0); self.regs = 0
            for i in range(3, len(n.children)): self.gen_stmt(n.children[i])
            r1 = self.gen_expr(Node('VAR', value=n.value)); step_r = self.gen_expr(n.children[2])
            self.emit(Opcode.ADD, rd=r1, rs1=r1, imm=step_r); self.emit(Opcode.SW, rs1=r1, rd=0, imm=addr); self.regs = 0
            self.emit(Opcode.JMP, imm=start_l); self.instrs[exit_f]['imm'] = len(self.instrs)

def main(src, tgt):
    with open(src, "r") as f: code = f.read()
    tokens = []
    regex = '|'.join('(?P<%s>%s)' % pair for pair in TOKEN_TYPES)
    for mo in re.finditer(regex, code):
        if mo.lastgroup != 'SKIP': tokens.append((mo.lastgroup, mo.group()))
    ast = Parser(tokens).parse_prog()
    print("--- AST ---"); [print(n) for n in ast]
    gen = CodeGen()
    [gen.gen_stmt(n) for n in ast]
    gen.emit(Opcode.HALT)
    res = bytearray()
    for i in gen.instrs:
        res.append(OPCODE_TO_CODE[i['opcode']])
        res.append((i['rd'] << 4) | i['rs1'])
        res.extend([(i['imm'] >> 8) & 0xFF, i['imm'] & 0xFF])
    with open(tgt, "wb") as f: f.write(res)
    with open(tgt + ".mem", "w") as f: json.dump(gen.mem, f)
    print(f"--- SUCCESS: {len(gen.instrs)} instrs ---")

if __name__ == "__main__": main(sys.argv[1], sys.argv[2])