import sys
import os
import re
import graphviz
import networkx as nx

from pycparser import parse_file, CParser

from cfg_builder import CFGBuilder
from analysis import ReachingDefinitions, LiveVariableAnalysis
from optimizations import run_all


def read_lines(c_file):
    with open(c_file) as f:
        return f.readlines()


def strip_comments(code):
    code = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)
    code = re.sub(r'//[^\n]*', '', code)
    return code


def parse_c_file(c_file):
    try:
        ast = parse_file(c_file, use_cpp=True, cpp_path='cpp', cpp_args=['-w'])
        return ast, None
    except Exception:
        pass

    try:
        with open(c_file) as f:
            code = f.read()
        code = strip_comments(code)
        ast = CParser().parse(code, filename=c_file)
        return ast, None
    except Exception as e:
        return None, str(e)


def get_error_line(error_msg):
    match = re.search(r':(\d+):(\d+):', error_msg)
    if match:
        return int(match.group(1)), int(match.group(2))
    return None, None


def parse_partial(lines, error_line):
    for cut in range(error_line - 1, 0, -1):
        partial_code = "".join(lines[:cut])
        partial_code = strip_comments(partial_code)
        open_braces = partial_code.count('{') - partial_code.count('}')
        partial_code += '\n' + '}' * open_braces
        try:
            ast = CParser().parse(partial_code, filename='<partial>')
            return ast
        except Exception:
            continue
    return None


def sync_labels(graph):
    from cfg_builder import get_stmt_label

    for node_id, data in graph.nodes(data=True):
        bb = data.get('block')
        if bb is None:
            continue

        if bb.stmts:
            new_label = chr(10).join(get_stmt_label(s) for s in bb.stmts)
        else:
            new_label = data.get('label', node_id)

        data['label'] = new_label
        bb.label = new_label


def draw_all_functions(builder, graph, output_file):
    dot = graphviz.Digraph()
    dot.attr(rankdir='TB', nodesep='0.4', ranksep='0.6')
    dot.attr('node', shape='rectangle', style='filled', fillcolor='white',
             fontname='Courier', fontsize='10')
    dot.attr('edge', fontname='Courier', fontsize='9')

    for func_name in builder.functions:
        subgraph = builder.get_function_subgraph(func_name)
        if subgraph is None:
            continue

        with dot.subgraph(name='cluster_' + func_name) as c:
            c.attr(label=func_name, fontname='Courier', fontsize='11',
                   style='dashed', color='black')

            for node_id, data in subgraph.nodes(data=True):
                label = data.get('label', node_id)
                is_error = data.get('is_error', False)
                kind = data.get('kind', '')

                if is_error:
                    c.node(node_id, label=label, fillcolor='#ffcccc',
                           color='red', fontcolor='red', penwidth='2')
                elif kind == 'start' or kind == 'end':
                    c.node(node_id, label=label, fillcolor='#e8f0ff')
                elif kind == 'control':
                    c.node(node_id, label=label, fillcolor='#fff2cc')
                else:
                    c.node(node_id, label=label)

            for src, dst, data in subgraph.edges(data=True):
                edge_label = data.get('label', '')
                c.edge(src, dst, label=edge_label)

    dot.render(output_file, format='png', cleanup=True)
    print("Saved: " + output_file + ".png")


def draw_error_graph(graph, output_file):
    dot = graphviz.Digraph()
    dot.attr(rankdir='TB', nodesep='0.4', ranksep='0.6')
    dot.attr('node', shape='rectangle', style='filled', fillcolor='white',
             fontname='Courier', fontsize='10')
    dot.attr('edge', fontname='Courier', fontsize='9')

    for node_id, data in graph.nodes(data=True):
        label = data.get('label', node_id)
        if data.get('is_error', False):
            dot.node(node_id, label=label, fillcolor='#ffcccc',
                     color='red', fontcolor='red', penwidth='2')
        else:
            dot.node(node_id, label=label)

    for src, dst, data in graph.edges(data=True):
        el = data.get('label', '')
        dot.edge(src, dst, label=el)

    dot.render(output_file, format='png', cleanup=True)
    print("Saved: " + output_file + ".png")


def find_last_node(graph):
    candidates = [n for n in graph.nodes if graph.out_degree(n) == 0]
    if candidates:
        return sorted(candidates, key=lambda n: int(n[1:]) if n[1:].isdigit() else 0)[-1]
    return None


def add_error_block(graph, error_line, error_col, bad_line, error_msg):
    label = (
        "ERROR at Line " + str(error_line) + "\n"
        + bad_line.strip() + "\n"
        + " " * (error_col - 1) + "^\n"
        + error_msg.strip()
    )
    graph.add_node("ERROR", label=label, is_error=True)
    last = find_last_node(graph)
    if last and last != "ERROR":
        graph.add_edge(last, "ERROR", label="error")
    return graph


def main():
    c_file = sys.argv[1] if len(sys.argv) > 1 else "test.c"

    if not os.path.exists(c_file):
        print("File not found: " + c_file)
        sys.exit(1)

    print("Input: " + c_file)
    lines = read_lines(c_file)

    print("\n--- Phase 1: Building CFG ---")
    ast, error = parse_c_file(c_file)

    if error is not None:
        error_line, error_col = get_error_line(error)

        print("PARSE ERROR detected!")
        if error_line:
            bad_line = lines[error_line - 1].rstrip() if error_line <= len(lines) else ""
            print("  Line  : " + str(error_line))
            print("  Code  : " + bad_line.strip())
            if error_col:
                print("          " + " " * (error_col - 1) + "^")
            msg_match = re.search(r':\d+:\d+:\s*(.*)', error)
            short_msg = msg_match.group(1) if msg_match else error
            print("  Error : " + short_msg)
        else:
            bad_line = ""
            short_msg = error

        print("\nBuilding partial CFG from valid code...")
        partial_ast = parse_partial(lines, error_line) if error_line else None

        if partial_ast:
            builder = CFGBuilder()
            graph = builder.build(partial_ast)
            print("Partial CFG: " + str(graph.number_of_nodes()) + " blocks from valid code")
        else:
            graph = nx.DiGraph()
            graph.add_node("B0", label="START: " + c_file, is_error=False)

        graph = add_error_block(graph, error_line, error_col or 1, bad_line, short_msg)
        draw_error_graph(graph, "cfg_original")
        print("Error highlighted in cfg_original.png")
        return

    builder = CFGBuilder()
    graph = builder.build(ast)
    print("Blocks: " + str(graph.number_of_nodes()))
    print("Edges : " + str(graph.number_of_edges()))
    print("Functions: " + ", ".join(builder.functions.keys()))

    draw_all_functions(builder, graph, "cfg_original")

    print("\n--- Phase 2: Static Analysis ---")
    rd = ReachingDefinitions(graph).analyze()
    la = LiveVariableAnalysis(graph).analyze()

    uninit = rd.get_uninitialized_uses()
    dead = la.get_dead_assignments()

    print("Uninitialized variable warnings: " + str(len(uninit)))
    for block_id, var in uninit:
        print("  WARNING: '" + var + "' used in " + block_id + " with no reaching definition")

    print("Dead assignment warnings: " + str(len(dead)))
    for block_id, var, msg in dead:
        print("  WARNING: " + msg + " in " + block_id)

    with open("analysis_report.txt", "w") as f:
        f.write(rd.report() + "\n\n")
        f.write(la.report() + "\n\n")
        f.write("=== Warnings ===\n")
        for bid, var in uninit:
            f.write("[UNINIT] '" + var + "' used in " + bid + "\n")
        for bid, var, msg in dead:
            f.write("[DEAD]   " + msg + " in " + bid + "\n")
    print("Analysis report saved: analysis_report.txt")

    print("\n--- Phase 3: Optimizations ---")
    results = run_all(graph, rd, la)
    for name, count in results.items():
        print("  " + name + ": " + str(count) + " change(s)")
    print("Total: " + str(sum(results.values())) + " change(s)")

    sync_labels(graph)
    draw_all_functions(builder, graph, "cfg_optimized")

    print("\nDone.")
    print("  cfg_original.png  - CFG before optimization")
    print("  cfg_optimized.png - CFG after optimization")


if __name__ == "__main__":
    main()
