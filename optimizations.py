from pycparser import c_ast
import networkx as nx


def is_constant(expr):
    return isinstance(expr, c_ast.Constant)


def const_value(expr):
    try:
        return int(expr.value)
    except Exception:
        try:
            return float(expr.value)
        except Exception:
            return None


def make_constant(value):
    if isinstance(value, float) and not value.is_integer():
        return c_ast.Constant(type="float", value=str(value))
    return c_ast.Constant(type="int", value=str(int(value)))


class ConstantFolder:
    OPS = {
        '+': lambda a, b: a + b,
        '-': lambda a, b: a - b,
        '*': lambda a, b: a * b,
        '/': lambda a, b: a // b if isinstance(a, int) and isinstance(b, int) else a / b,
        '%': lambda a, b: a % b,
        '<': lambda a, b: int(a < b),
        '>': lambda a, b: int(a > b),
        '<=': lambda a, b: int(a <= b),
        '>=': lambda a, b: int(a >= b),
        '==': lambda a, b: int(a == b),
        '!=': lambda a, b: int(a != b),
    }

    def run(self, graph):
        count = 0
        for _, data in graph.nodes(data=True):
            bb = data.get('block')
            if bb:
                for stmt in bb.stmts:
                    count += self.fold(stmt)
        return graph, count

    def fold(self, node):
        if node is None:
            return 0
        count = 0
        for attr, child in list(node.children()):
            if isinstance(child, c_ast.BinaryOp):
                count += self.fold(child)
                result = self.try_fold(child)
                if result is not None:
                    setattr(node, attr.split('[')[0], result)
                    count += 1
            else:
                count += self.fold(child)
        return count

    def try_fold(self, node):
        if not (is_constant(node.left) and is_constant(node.right)):
            return None
        op = self.OPS.get(node.op)
        if op is None:
            return None
        a = const_value(node.left)
        b = const_value(node.right)
        if a is None or b is None:
            return None
        if node.op in ('/', '%') and b == 0:
            return None
        try:
            return make_constant(op(a, b))
        except Exception:
            return None


class ConstantPropagator:
    def run(self, graph, reaching_defs):
        count = 0
        loop_nodes = self.find_loop_nodes(graph)

        def_values = {}
        for node_id, data in graph.nodes(data=True):
            bb = data.get('block')
            if bb is None:
                continue
            for stmt in bb.stmts:
                var = self.get_defined(stmt)
                if var:
                    def_values[(var, node_id)] = self.get_const_rhs(stmt)

        for node_id, data in graph.nodes(data=True):
            # Safety fix: do not propagate constants inside loops.
            # Otherwise i=0 may incorrectly change every loop iteration to i=0.
            if node_id in loop_nodes:
                continue

            bb = data.get('block')
            if bb is None:
                continue

            reaching = reaching_defs.IN.get(node_id, set())
            env = {}
            grouped = {}
            for var, src in reaching:
                grouped.setdefault(var, []).append(def_values.get((var, src)))

            for var, vals in grouped.items():
                vals = [v for v in vals if v is not None]
                if len(vals) > 0 and len(set(vals)) == 1:
                    env[var] = vals[0]

            for stmt in bb.stmts:
                count += self.propagate_stmt(stmt, env)
                var = self.get_defined(stmt)
                if var:
                    rhs_const = self.get_const_rhs(stmt)
                    if rhs_const is not None:
                        env[var] = rhs_const
                    elif var in env:
                        del env[var]

        return graph, count

    def find_loop_nodes(self, graph):
        loop_nodes = set()
        for cycle in nx.simple_cycles(graph):
            loop_nodes.update(cycle)
        return loop_nodes

    def get_defined(self, stmt):
        if isinstance(stmt, c_ast.Assignment):
            if isinstance(stmt.lvalue, c_ast.ID):
                return stmt.lvalue.name
        if isinstance(stmt, c_ast.Decl) and stmt.init is not None:
            return stmt.name
        return None

    def get_const_rhs(self, stmt):
        rhs = None
        if isinstance(stmt, c_ast.Assignment):
            rhs = stmt.rvalue
        elif isinstance(stmt, c_ast.Decl) and stmt.init:
            rhs = stmt.init
        if rhs and is_constant(rhs):
            return const_value(rhs)
        return None

    def propagate_stmt(self, stmt, env):
        if isinstance(stmt, c_ast.Assignment):
            return self.replace_ids(stmt.rvalue, env, stmt, 'rvalue')
        if isinstance(stmt, c_ast.Decl):
            if stmt.init is not None:
                return self.replace_ids(stmt.init, env, stmt, 'init')
            return 0
        if isinstance(stmt, c_ast.Return):
            if stmt.expr is not None:
                return self.replace_ids(stmt.expr, env, stmt, 'expr')
            return 0
        return self.replace_ids(stmt, env, None, None)

    def replace_ids(self, node, env, parent=None, parent_attr=None):
        if node is None:
            return 0
        if isinstance(node, c_ast.ID) and node.name in env:
            if parent is not None and parent_attr is not None:
                setattr(parent, parent_attr, make_constant(env[node.name]))
                return 1
            return 0
        count = 0
        for attr, child in list(node.children()):
            real_attr = attr.split('[')[0]
            if '[' not in attr:
                if isinstance(child, c_ast.ID) and child.name in env:
                    setattr(node, real_attr, make_constant(env[child.name]))
                    count += 1
                else:
                    count += self.replace_ids(child, env, node, real_attr)
            else:
                count += self.replace_ids(child, env, None, None)
        return count


class DeadCodeEliminator:
    def run(self, graph, live_analysis):
        count = 0
        dead_set = {(b, v) for b, v, _ in live_analysis.get_dead_assignments()}
        nodes_to_remove = []

        for node_id, data in list(graph.nodes(data=True)):
            bb = data.get('block')
            if bb is None:
                continue
            old_len = len(bb.stmts)
            new_stmts = []
            for stmt in bb.stmts:
                var = self.get_defined(stmt)
                if var and (node_id, var) in dead_set:
                    count += 1
                    continue
                new_stmts.append(stmt)
            bb.stmts = new_stmts
            if old_len > 0 and len(new_stmts) == 0 and data.get('kind') == 'stmt':
                nodes_to_remove.append(node_id)

        self.remove_nodes_and_reconnect(graph, nodes_to_remove)
        return graph, count

    def remove_nodes_and_reconnect(self, graph, nodes_to_remove):
        for node in nodes_to_remove:
            if node not in graph:
                continue
            preds = list(graph.predecessors(node))
            succs = list(graph.successors(node))
            for p in preds:
                for s in succs:
                    if p != s:
                        graph.add_edge(p, s, label="optimized")
            graph.remove_node(node)

    def get_defined(self, stmt):
        if isinstance(stmt, c_ast.Assignment):
            if isinstance(stmt.lvalue, c_ast.ID):
                return stmt.lvalue.name
        if isinstance(stmt, c_ast.Decl) and stmt.init is not None:
            return stmt.name
        return None


class IfSimplifier:
    def run(self, graph):
        count = 0
        for node_id, data in list(graph.nodes(data=True)):
            label = data.get('label', '')
            if not (label.startswith('if (') and label.endswith(')')):
                continue
            cond = label[4:-1].strip()
            if cond not in ('0', '1'):
                continue

            succs = list(graph.successors(node_id))
            preds = list(graph.predecessors(node_id))
            if len(succs) == 0:
                continue

            # CFGBuilder creates true branch first, false branch second.
            true_start = succs[0]
            false_start = succs[1] if len(succs) > 1 else None
            chosen_start = true_start if cond == '1' else false_start
            removed_start = false_start if cond == '1' else true_start
            if chosen_start is None:
                continue

            merge = self.find_common_merge(graph, true_start, false_start)

            for p in preds:
                if p in graph and chosen_start in graph:
                    graph.add_edge(p, chosen_start, label='if simplified')

            if node_id in graph:
                graph.remove_node(node_id)
                count += 1

            if removed_start is not None:
                for r in list(self.nodes_until_merge(graph, removed_start, merge)):
                    if r in graph:
                        graph.remove_node(r)
                        count += 1

            # Remove useless merge if only one path now reaches it.
            if merge is not None and merge in graph and graph.in_degree(merge) <= 1:
                self.remove_passthrough_node(graph, merge)
                count += 1

        return graph, count

    def find_common_merge(self, graph, a, b):
        if a is None or b is None or a not in graph or b not in graph:
            return None
        common = (nx.descendants(graph, a) | {a}) & (nx.descendants(graph, b) | {b})
        merges = [n for n in common if graph.nodes[n].get('label') == 'merge']
        if not merges:
            return None
        return sorted(merges, key=self.node_number)[0]

    def nodes_until_merge(self, graph, start, merge):
        if start is None or start not in graph:
            return set()
        remove = set()
        stack = [start]
        while stack:
            node = stack.pop()
            if node == merge or node in remove or node not in graph:
                continue
            remove.add(node)
            for succ in list(graph.successors(node)):
                if succ != merge:
                    stack.append(succ)
        return remove

    def remove_passthrough_node(self, graph, node):
        preds = list(graph.predecessors(node))
        succs = list(graph.successors(node))
        for p in preds:
            for s in succs:
                if p != s and p in graph and s in graph:
                    graph.add_edge(p, s, label='if simplified')
        if node in graph:
            graph.remove_node(node)

    def node_number(self, node):
        return int(node[1:]) if len(node) > 1 and node[1:].isdigit() else 10**9


class UnreachableCodeRemover:
    def run(self, graph):
        roots = [n for n, d in graph.nodes(data=True) if d.get('kind') == 'start']
        reachable = set()
        for root in roots:
            if root in graph:
                reachable.add(root)
                reachable |= nx.descendants(graph, root)
        unreachable = set(graph.nodes) - reachable
        for node in list(unreachable):
            graph.remove_node(node)
        return graph, len(unreachable)


def run_all(graph, reaching_defs=None, live_analysis=None):
    results = {}

    graph, n = ConstantFolder().run(graph)
    results['constant folding'] = n

    if reaching_defs:
        graph, n = ConstantPropagator().run(graph, reaching_defs)
        results['constant propagation'] = n
    else:
        results['constant propagation'] = 0

    graph, n = ConstantFolder().run(graph)
    results['constant folding after propagation'] = n

    if live_analysis:
        graph, n = DeadCodeEliminator().run(graph, live_analysis)
        results['dead code elimination'] = n
    else:
        results['dead code elimination'] = 0

    graph, n = IfSimplifier().run(graph)
    results['if simplification'] = n

    graph, n = UnreachableCodeRemover().run(graph)
    results['unreachable code removal'] = n

    return results
