import android.app.UiAutomation;
import android.accessibilityservice.AccessibilityServiceInfo;
import android.graphics.Rect;
import android.os.HandlerThread;
import android.os.Looper;
import android.util.Xml;
import android.view.accessibility.AccessibilityNodeInfo;
import java.io.FileOutputStream;
import org.xmlpull.v1.XmlSerializer;

/** Read the current accessibility tree without requiring an idle animation loop. */
public final class UiHierarchy {
    private static String text(CharSequence value) {
        return value == null ? "" : value.toString();
    }

    private static void node(XmlSerializer xml, AccessibilityNodeInfo item, int depth)
            throws Exception {
        if (depth > 64 || !item.isVisibleToUser()) return;
        xml.startTag(null, "node");
        xml.attribute(null, "package", text(item.getPackageName()));
        xml.attribute(null, "text", text(item.getText()));
        xml.attribute(null, "content-desc", text(item.getContentDescription()));
        xml.attribute(null, "class", text(item.getClassName()));
        xml.attribute(null, "resource-id", text(item.getViewIdResourceName()));
        xml.attribute(null, "checkable", Boolean.toString(item.isCheckable()));
        xml.attribute(null, "checked", Boolean.toString(item.isChecked()));
        xml.attribute(null, "clickable", Boolean.toString(item.isClickable()));
        xml.attribute(null, "enabled", Boolean.toString(item.isEnabled()));
        Rect bounds = new Rect();
        item.getBoundsInScreen(bounds);
        xml.attribute(null, "bounds", bounds.toShortString());
        for (int i = 0; i < item.getChildCount(); i++) {
            AccessibilityNodeInfo child = item.getChild(i);
            if (child != null) node(xml, child, depth + 1);
        }
        xml.endTag(null, "node");
    }

    public static void main(String[] args) throws Exception {
        // Android 17's accessibility client creates a handler on the main looper.
        Looper.prepareMainLooper();
        HandlerThread thread = new HandlerThread("hierarchy");
        thread.start();
        // app_process exposes the platform connection used by the uiautomator command.
        Class<?> connectionType = Class.forName("android.app.IUiAutomationConnection");
        Object connection = Class.forName("android.app.UiAutomationConnection")
                .getDeclaredConstructor().newInstance();
        UiAutomation automation = UiAutomation.class
                .getDeclaredConstructor(Looper.class, connectionType)
                .newInstance(thread.getLooper(), connection);
        try {
            UiAutomation.class.getDeclaredMethod("connect", int.class).invoke(automation, 0);
            AccessibilityServiceInfo service = automation.getServiceInfo();
            service.flags |= AccessibilityServiceInfo.FLAG_INCLUDE_NOT_IMPORTANT_VIEWS
                    | AccessibilityServiceInfo.FLAG_REPORT_VIEW_IDS;
            automation.setServiceInfo(service);
            AccessibilityNodeInfo root = null;
            for (int i = 0; i < 20 && root == null; i++) {
                root = automation.getRootInActiveWindow();
                if (root == null) Thread.sleep(200);
            }
            if (root == null) throw new IllegalStateException("No active accessibility root");
            try (FileOutputStream output = new FileOutputStream(args[0])) {
                XmlSerializer xml = Xml.newSerializer();
                xml.setOutput(output, "UTF-8");
                xml.startDocument("UTF-8", true);
                xml.startTag(null, "hierarchy");
                node(xml, root, 0);
                xml.endTag(null, "hierarchy");
                xml.endDocument();
            }
        } finally {
            UiAutomation.class.getDeclaredMethod("disconnect").invoke(automation);
            thread.quitSafely();
        }
    }
}
