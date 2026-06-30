int add(int a, int b) {
    int temp = 0;      // dead
    int res = a + b;
    return res;
}

int compute() {
    int x = 2;
    int y = 3;
    int z;

    z = x * y + 4;

    if (1) {
        z = z + 10;
    } else {
        z = z - 10;
    }

    return z;
}

int main() {
    int a = 5;
    int b = 6;
    int c;

    c = add(a, b);

    if (0) {
        c = c + 100;
    }

    return c;
}