n = read();
v0 = read();
v1 = read();
v2 = read();
v3 = read();

swapped = 1;
for (pass = 0, 3, 1) {
    if (v0 > v1) { tmp = v0; v0 = v1; v1 = tmp; }
    if (v1 > v2) { tmp = v1; v1 = v2; v2 = tmp; }
    if (v2 > v3) { tmp = v2; v2 = v3; v3 = tmp; }
}

print(v0);
print(v1);
print(v2);
print(v3);