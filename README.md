# Compiler Optimization Framework using Data Flow Analysis

## Overview

This project implements a compiler optimization framework in Python using **pycparser**, **NetworkX**, and **Graphviz**. The tool parses C programs, constructs Control Flow Graphs (CFGs), performs static analysis, applies multiple optimization passes, and visualizes the CFG before and after optimization.

The project demonstrates fundamental compiler concepts including data flow analysis, code optimization, and CFG construction.

---

## Features

### Control Flow Graph (CFG) Construction

* Parses C source code using pycparser.
* Builds CFGs for all functions.
* Supports conditional branches and merge nodes.
* Generates graphical CFG visualizations.

### Static Analysis

#### Reaching Definitions Analysis

* Tracks variable definitions throughout the CFG.
* Detects variables used without valid reaching definitions.

#### Live Variable Analysis

* Computes live-in and live-out variable sets.
* Detects dead assignments.

### Compiler Optimizations

#### Constant Folding

Evaluates constant expressions at compile time.

Example:

```c
int x = 2 * 3 + 4;
```

Optimized to:

```c
int x = 10;
```

#### Constant Propagation

Propagates known constant values through the program.

Example:

```c
int a = 5;
int b = a + 2;
```

Optimized to:

```c
int b = 5 + 2;
```

#### Dead Code Elimination

Removes assignments whose values are never used.

Example:

```c
int temp = 0;
```

#### If Simplification

Simplifies constant conditional statements.

Example:

```c
if (1) {
    x = x + 1;
}
else {
    x = x - 1;
}
```

Optimized to:

```c
x = x + 1;
```

#### Unreachable Code Removal

Removes CFG nodes that cannot be reached after optimization.

---

## Project Structure

```text
Compiler-Optimization-Framework/
│
├── main.py
├── analysis.py
├── optimizations.py
├── cfg_builder.py
├── test.c
├── cfg_original.png
├── cfg_optimized.png
├── analysis_report.txt
├── requirements.txt
└── README.md
```

---

## Technologies Used

* Python 3
* pycparser
* NetworkX
* Graphviz

---

## Installation

### Clone Repository

```bash
git clone https://github.com/<your-username>/Compiler-Optimization-Framework.git
cd Compiler-Optimization-Framework
```

### Install Dependencies

Ubuntu/Linux:

```bash
sudo apt install graphviz
```

Install Python packages:

```bash
pip3 install pycparser networkx graphviz --break-system-packages
```

---

## Running the Project

Run the analyzer on a C source file:

```bash
python3 main.py test.c
```

---

## Example Input

```c
int compute() {
    int x = 2;
    int y = 3;
    int z;

    z = x * y + 4;

    if (1) {
        z = z + 10;
    }

    return z;
}
```

---

## Example Output

```text
--- Phase 1: Building CFG ---
Blocks: 26
Edges : 25
Functions: add, compute, main

--- Phase 2: Static Analysis ---
Uninitialized variable warnings: 3
Dead assignment warnings: 1

--- Phase 3: Optimizations ---
constant folding: 0 change(s)
constant propagation: 2 change(s)
constant folding after propagation: 2 change(s)
dead code elimination: 1 change(s)
if simplification: 6 change(s)
unreachable code removal: 0 change(s)

Total: 11 change(s)
```

---

## Generated Files

### CFG Before Optimization

```text
cfg_original.png
```

Visual representation of the original program CFG.

### CFG After Optimization

```text
cfg_optimized.png
```

Shows CFG after optimization passes.

### Analysis Report

```text
analysis_report.txt
```

Contains:

* Reaching Definitions Results
* Live Variable Analysis Results
* Uninitialized Variable Warnings
* Dead Assignment Warnings

---

## Static Analyses Implemented

### Reaching Definitions

Data-flow equation:

```text
IN[B] = Union(OUT[P]) for all predecessors P

OUT[B] = GEN[B] ∪ (IN[B] − KILL[B])
```

### Live Variable Analysis

Data-flow equation:

```text
OUT[B] = Union(IN[S]) for all successors S

IN[B] = USE[B] ∪ (OUT[B] − DEF[B])
```

---

## Optimization Pipeline

```text
1. CFG Construction
2. Reaching Definitions Analysis
3. Live Variable Analysis
4. Constant Folding
5. Constant Propagation
6. Dead Code Elimination
7. If Simplification
8. Unreachable Code Removal
9. CFG Visualization
```

---

## Known Limitations

* Function parameters are not yet treated as entry definitions.
* Function-call identifiers may occasionally appear in uninitialized variable warnings.
* Interprocedural analysis is not implemented.
* SSA-based optimizations are not implemented.

---

## Future Enhancements

* Common Subexpression Elimination (CSE)
* Copy Propagation
* Loop Invariant Code Motion
* SSA Form Generation
* Dominator Tree Construction
* Register Allocation
* Interprocedural Analysis

---

## Learning Outcomes

This project demonstrates understanding of:

* Compiler Design
* Static Program Analysis
* Data Flow Analysis
* Control Flow Graph Construction
* Optimization Techniques
* Program Visualization

---
