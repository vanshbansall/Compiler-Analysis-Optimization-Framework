from pycparser import c_ast
import networkx as nx


def get_stmt_label(stmt):
    if isinstance(stmt, c_ast.Assignment):
        return expr_to_str(stmt.lvalue) + " " + stmt.op + " " + expr_to_str(stmt.rvalue)
    if isinstance(stmt, c_ast.Decl):
        if stmt.init is not None:
            return stmt.name + " = " + expr_to_str(stmt.init)
        return "declare " + stmt.name
    if isinstance(stmt, c_ast.Return):
        if stmt.expr:
            return "return " + expr_to_str(stmt.expr)
        return "return"
    if isinstance(stmt, c_ast.FuncCall):
        return expr_to_str(stmt.name) + "(...)"
    if isinstance(stmt, c_ast.UnaryOp):
        return stmt.op + expr_to_str(stmt.expr)
    return type(stmt).__name__


def expr_to_str(expr):
    if expr is None:
        return ""
    if isinstance(expr, c_ast.ID):
        return expr.name
    if isinstance(expr, c_ast.Constant):
        return expr.value
    if isinstance(expr, c_ast.BinaryOp):
        return expr_to_str(expr.left) + " " + expr.op + " " + expr_to_str(expr.right)
    if isinstance(expr, c_ast.UnaryOp):
        return expr.op + expr_to_str(expr.expr)
    if isinstance(expr, c_ast.FuncCall):
        return expr_to_str(expr.name) + "(...)"
    if isinstance(expr, c_ast.ArrayRef):
        return expr_to_str(expr.name) + "[" + expr_to_str(expr.subscript) + "]"
    if isinstance(expr, c_ast.ExprList):
        return ", ".join(expr_to_str(e) for e in expr.exprs)
    if isinstance(expr, c_ast.Cast):
        return "cast(" + expr_to_str(expr.expr) + ")"
    return type(expr).__name__


class BasicBlock:
    def __init__(self, block_id, label):
        self.block_id = block_id
        self.label = label
        self.stmts = []


class CFGBuilder:

    def __init__(self):
        self.graph = nx.DiGraph()
        self.counter = 0
        self.functions = {}

    def new_block(self, label):
        bid = "B" + str(self.counter)
        self.counter += 1
        bb = BasicBlock(bid, label)
        self.graph.add_node(bid, label=label, block=bb, kind=self.block_kind(label))
        return bb

    def block_kind(self, label):
        if label.startswith("START"):
            return "start"
        if label.startswith("END"):
            return "end"
        if label.startswith("if") or label.startswith("while") or label.startswith("for cond"):
            return "control"
        if label.startswith("after") or label == "merge" or label.startswith("do-while"):
            return "control"
        return "stmt"

    def add_edge(self, src, dst, label=""):
        self.graph.add_edge(src.block_id, dst.block_id, label=label)

    def build(self, ast):
        for item in ast.ext:
            if isinstance(item, c_ast.FuncDef):
                func_name = item.decl.name
                start = self.new_block("START: " + func_name)
                self.functions[func_name] = start.block_id
                last = self.visit_compound(item.body, start)
                end = self.new_block("END: " + func_name)
                self.add_edge(last, end)
        return self.graph

    def get_function_subgraph(self, func_name):
        if func_name not in self.functions:
            return None
        start_id = self.functions[func_name]
        if start_id not in self.graph:
            return nx.DiGraph()
        reachable = nx.descendants(self.graph, start_id) | {start_id}
        return self.graph.subgraph(reachable).copy()

    def visit_compound(self, compound, prev):
        if compound is None or compound.block_items is None:
            return prev
        for stmt in compound.block_items:
            prev = self.visit_stmt(stmt, prev)
        return prev

    def visit_stmt(self, stmt, prev):
        if isinstance(stmt, c_ast.If):
            return self.visit_if(stmt, prev)
        elif isinstance(stmt, c_ast.While):
            return self.visit_while(stmt, prev)
        elif isinstance(stmt, c_ast.For):
            return self.visit_for(stmt, prev)
        elif isinstance(stmt, c_ast.DoWhile):
            return self.visit_dowhile(stmt, prev)
        elif isinstance(stmt, c_ast.Compound):
            return self.visit_compound(stmt, prev)
        else:
            block = self.new_block(get_stmt_label(stmt))
            block.stmts.append(stmt)
            self.add_edge(prev, block)
            return block

    def visit_if(self, stmt, prev):
        cond = self.new_block("if (" + expr_to_str(stmt.cond) + ")")
        self.add_edge(prev, cond)

        then_end = self.visit_stmt(stmt.iftrue, cond) if stmt.iftrue else cond
        else_end = self.visit_stmt(stmt.iffalse, cond) if stmt.iffalse else cond

        merge = self.new_block("merge")
        self.add_edge(then_end, merge, "true")
        self.add_edge(else_end, merge, "false")
        return merge

    def visit_while(self, stmt, prev):
        cond = self.new_block("while (" + expr_to_str(stmt.cond) + ")")
        self.add_edge(prev, cond)

        body_end = self.visit_stmt(stmt.stmt, cond)
        self.add_edge(body_end, cond, "true")

        exit_block = self.new_block("after while")
        self.add_edge(cond, exit_block, "false")
        return exit_block

    def visit_for(self, stmt, prev):
        if stmt.init:
            init = self.new_block("for init: " + get_stmt_label(stmt.init))
            init.stmts = [stmt.init]
            self.add_edge(prev, init)
            prev = init

        cond_label = "for cond: " + expr_to_str(stmt.cond) if stmt.cond else "for cond: true"
        cond = self.new_block(cond_label)
        self.add_edge(prev, cond)

        body_end = self.visit_stmt(stmt.stmt, cond)

        if stmt.next:
            inc = self.new_block("for inc: " + expr_to_str(stmt.next))
            inc.stmts = [stmt.next]
            self.add_edge(body_end, inc)
            self.add_edge(inc, cond, "true")
        else:
            self.add_edge(body_end, cond, "true")

        exit_block = self.new_block("after for")
        self.add_edge(cond, exit_block, "false")
        return exit_block

    def visit_dowhile(self, stmt, prev):
        body_start = self.new_block("do-while body")
        self.add_edge(prev, body_start)

        body_end = self.visit_stmt(stmt.stmt, body_start)

        cond = self.new_block("while (" + expr_to_str(stmt.cond) + ")")
        self.add_edge(body_end, cond)
        self.add_edge(cond, body_start, "true")

        exit_block = self.new_block("after do-while")
        self.add_edge(cond, exit_block, "false")
        return exit_block
