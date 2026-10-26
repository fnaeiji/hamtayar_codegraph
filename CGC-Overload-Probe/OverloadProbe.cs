namespace CgcOverloadProbe;

public class Calculator
{
    public int Compute(int value) => value + 1;
    public int Compute(string value) => value.Length;
    public int Compute(int left, int right) => left + right;
}

public class Reporter
{
    public string Compute(int value) => $"Value: {value}";
}

public class ProbeRunner
{
    public void Run()
    {
        var calculator = new Calculator();
        calculator.Compute(5);
        calculator.Compute("hello");
        calculator.Compute(2, 3);

        var reporter = new Reporter();
        reporter.Compute(5);
    }
}
