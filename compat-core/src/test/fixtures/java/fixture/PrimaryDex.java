package fixture;

public final class PrimaryDex {
    public static String tablet() {
        Object marker = new Object();
        marker.hashCode();
        return "tablet-anchor";
    }

    public static String unrelated() {
        return "unrelated-literal";
    }
}
