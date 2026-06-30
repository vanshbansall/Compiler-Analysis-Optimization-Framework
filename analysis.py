from pycparser import c_ast


def get_defined(stmt):
    if isinstance(stmt, c_ast.Assignment):
        if isinstance(stmt.lvalue, c_ast.ID):
            return stmt.lvalue.name
    if isinstance(stmt, c_ast.Decl) and stmt.init is not None:
        return stmt.name
    if isinstance(stmt, c_ast.UnaryOp) and stmt.op in ('p++', 'p--', '++', '--'):
        if isinstance(stmt.expr, c_ast.ID):
            return stmt.expr.name
    return None


def get_used(stmt):
    used = set()

    def walk(node):
        if node is None:
            return
        if isinstance(node, c_ast.ID):
            used.add(node.name)
        for _, child in node.children():
            walk(child)

    if isinstance(stmt, c_ast.Assignment):
        walk(stmt.rvalue)
        if isinstance(stmt.lvalue, c_ast.ArrayRef):
            walk(stmt.lvalue)
    elif isinstance(stmt, c_ast.Decl) and stmt.init:
        walk(stmt.init)
    else:
        walk(stmt)

    return used


class ReachingDefinitions:
    def __init__(self, graph):
        self.graph = graph
        self.IN = {}
        self.OUT = {}
        self.gen = {}
        self.kill = {}
        self.all_defs = set()

    def analyze(self):
        self.compute_gen_kill()
        self.iterate()
        return self

    def compute_gen_kill(self):
        for node_id, data in self.graph.nodes(data=True):
            bb = data.get('block')
            if bb is None:
                continue
            for stmt in bb.stmts:
                var = get_defined(stmt)
                if var:
                    self.all_defs.add((var, node_id))

        for node_id, data in self.graph.nodes(data=True):
            gen = set()
            kill = set()
            bb = data.get('block')
            if bb:
                for stmt in bb.stmts:
                    var = get_defined(stmt)
                    if var:
                        d = (var, node_id)
                        gen = {x for x in gen if x[0] != var}
                        gen.add(d)
                        for other in self.all_defs:
                            if other[0] == var and other != d:
                                kill.add(other)
            self.gen[node_id] = gen
            self.kill[node_id] = kill
            self.IN[node_id] = set()
            self.OUT[node_id] = set(gen)

    def iterate(self):
        changed = True
        while changed:
            changed = False
            for node_id in list(self.graph.nodes):
                new_in = set()
                for pred in self.graph.predecessors(node_id):
                    new_in |= self.OUT.get(pred, set())

                new_out = self.gen.get(node_id, set()) | (new_in - self.kill.get(node_id, set()))

                if new_in != self.IN.get(node_id, set()) or new_out != self.OUT.get(node_id, set()):
                    self.IN[node_id] = new_in
                    self.OUT[node_id] = new_out
                    changed = True

    def get_uninitialized_uses(self):
        warnings = []
        for node_id, data in self.graph.nodes(data=True):
            bb = data.get('block')
            if bb is None:
                continue
            defined_vars = {var for var, _ in self.IN.get(node_id, set())}
            for stmt in bb.stmts:
                var_defined_here = get_defined(stmt)
                for var in get_used(stmt):
                    if var != var_defined_here and var not in defined_vars:
                        warnings.append((node_id, var))
        return warnings

    def report(self):
        lines = ["=== Reaching Definitions ==="]
        for node_id in self.graph.nodes:
            defs = self.IN.get(node_id, set())
            if defs:
                desc = ", ".join(v + "@" + b for v, b in sorted(defs))
                lines.append("  " + node_id + ": " + desc)
        return "\n".join(lines)


class LiveVariableAnalysis:
    def __init__(self, graph):
        self.graph = graph
        self.IN = {}
        self.OUT = {}
        self.use = {}
        self.defn = {}

    def analyze(self):
        self.compute_use_def()
        self.iterate()
        return self

    def compute_use_def(self):
        for node_id, data in self.graph.nodes(data=True):
            use = set()
            defn = set()
            bb = data.get('block')
            if bb:
                for stmt in bb.stmts:
                    for var in get_used(stmt):
                        if var not in defn:
                            use.add(var)
                    var = get_defined(stmt)
                    if var:
                        defn.add(var)
            self.use[node_id] = use
            self.defn[node_id] = defn
            self.IN[node_id] = set()
            self.OUT[node_id] = set()

    def iterate(self):
        changed = True
        while changed:
            changed = False
            for node_id in reversed(list(self.graph.nodes)):
                new_out = set()
                for succ in self.graph.successors(node_id):
                    new_out |= self.IN.get(succ, set())

                new_in = self.use.get(node_id, set()) | (new_out - self.defn.get(node_id, set()))

                if new_out != self.OUT.get(node_id, set()) or new_in != self.IN.get(node_id, set()):
                    self.OUT[node_id] = new_out
                    self.IN[node_id] = new_in
                    changed = True

    def get_dead_assignments(self):
        dead = []
        for node_id, data in self.graph.nodes(data=True):
            bb = data.get('block')
            if bb is None:
                continue
            live = set(self.OUT.get(node_id, set()))
            for stmt in reversed(bb.stmts):
                var = get_defined(stmt)
                if var and var not in live:
                    dead.append((node_id, var, "dead assignment to '" + var + "'"))
                if var:
                    live.discard(var)
                live |= get_used(stmt)
        return dead

    def report(self):
        lines = ["=== Live Variable Analysis ==="]
        for node_id in self.graph.nodes:
            live = self.IN.get(node_id, set())
            if live:
                lines.append("  " + node_id + " live-in: " + str(sorted(live)))
        return "\n".join(lines)
