package verun.runtime.evaluator;

/** Immutable binding marker used by Versa const declarations. */
public final class ConstantValue {
    public final Object value;
    public ConstantValue(Object value) { this.value = value; }
}
