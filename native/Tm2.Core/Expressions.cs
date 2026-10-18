namespace Tm2.Core;

public sealed class UnsupportedOperation(string message) : Exception(message);

// Native reconstruction of the measured main-engine expression subset.
// It interprets game script expressions, never PlayStation CPU instructions.
public sealed class Expression
{
    public int Op { get; private init; }
    public int Value { get; private init; }
    public Expression? Left { get; private init; }
    public Expression? Right { get; private init; }
    public static Expression Decode(byte[] bytes)
    {
        int p = 0;
        var expr = Parse(bytes, ref p, 0);
        if (p != bytes.Length) throw new InvalidDataException("Trailing expression bytes.");
        return expr;
    }
    private static byte Take(byte[] b, ref int p)
    {
        if (p >= b.Length) throw new InvalidDataException("Truncated expression.");
        return b[p++];
    }
    private static Expression Parse(byte[] b, ref int p, int depth)
    {
        if (depth > 64) throw new InvalidDataException("Expression nesting limit exceeded.");
        int op = Take(b, ref p);
        if (op == 0x40) return Parse(b, ref p, depth + 1);
        if (op == 0x4e)
        {
            int low = Take(b, ref p), high = Take(b, ref p);
            return new() { Op = op, Value = (short)(low | high << 8) };
        }
        if (op == 0x4f)
        {
            int index = Take(b, ref p);
            if (index > 15) throw new UnsupportedOperation($"State query 4F/{index:X2} is not reconstructed.");
            return new() { Op = op, Value = index };
        }
        if (op == 0x4d)
        {
            int index = Take(b, ref p);
            if (index > 15) throw new UnsupportedOperation($"Assignment target 4D/{index:X2} is not reconstructed.");
            return new() { Op = op, Value = index, Left = Parse(b, ref p, depth + 1) };
        }
        if (op is 0x46 or 0x5a)
            return new() { Op = op, Left = Parse(b, ref p, depth + 1) };
        if ((op >= 0x41 && op <= 0x45) || (op >= 0x47 && op <= 0x4c) || op is 0x58 or 0x59 or 0x5b)
        {
            var left = Parse(b, ref p, depth + 1);
            var right = Parse(b, ref p, depth + 1);
            return new() { Op = op, Left = left, Right = right };
        }
        throw new UnsupportedOperation($"Expression opcode {op:X2} is not reconstructed.");
    }
    public int Evaluate(int[] variables)
    {
        if (variables.Length != 16) throw new ArgumentException("Expected sixteen script registers.");
        if (Op == 0x4e) return Value;
        if (Op == 0x4f) return variables[Value];
        int a = Left!.Evaluate(variables);
        if (Op == 0x4d) return variables[Value] = a;
        if (Op == 0x46) return unchecked(-a);
        if (Op == 0x5a) return a == 0 ? 1 : 0;
        // The original evaluator eagerly evaluates both operands, including logical operators.
        int b = Right!.Evaluate(variables);
        return Op switch
        {
            0x41 => unchecked(a + b), 0x42 => unchecked(a - b), 0x43 => unchecked(a * b),
            0x44 => Divide(a, b), 0x45 => Remainder(a, b),
            0x47 => a < b ? 1 : 0, 0x48 => a > b ? 1 : 0,
            0x49 => a <= b ? 1 : 0, 0x4a => a >= b ? 1 : 0,
            0x4b => a == b ? 1 : 0, 0x4c => a != b ? 1 : 0,
            0x58 => a != 0 || b != 0 ? 1 : 0, 0x59 => a != 0 && b != 0 ? 1 : 0,
            0x5b => 0,
            _ => throw new UnsupportedOperation($"Expression opcode {Op:X2} is not reconstructed.")
        };
    }
    private static int Divide(int a, int b)
    {
        if (b == 0) throw new UnsupportedOperation("Divide by zero requires original exception behavior.");
        return a == int.MinValue && b == -1 ? int.MinValue : a / b;
    }
    private static int Remainder(int a, int b)
    {
        if (b == 0) throw new UnsupportedOperation("Remainder by zero requires original exception behavior.");
        return a == int.MinValue && b == -1 ? 0 : a % b;
    }
}
