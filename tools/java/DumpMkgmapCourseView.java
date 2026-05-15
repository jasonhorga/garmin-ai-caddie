import uk.me.parabola.imgfmt.Utils;
import uk.me.parabola.imgfmt.app.Area;
import uk.me.parabola.imgfmt.app.Coord;
import uk.me.parabola.imgfmt.app.Label;
import uk.me.parabola.imgfmt.fs.ImgChannel;
import uk.me.parabola.imgfmt.app.lbl.LBLFileReader;
import uk.me.parabola.imgfmt.app.trergn.RGNFileReader;
import uk.me.parabola.imgfmt.app.trergn.TREFileReader;
import uk.me.parabola.imgfmt.app.trergn.Point;
import uk.me.parabola.imgfmt.app.trergn.Polygon;
import uk.me.parabola.imgfmt.app.trergn.Polyline;
import uk.me.parabola.imgfmt.app.trergn.Subdivision;
import uk.me.parabola.imgfmt.app.trergn.Zoom;

import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;

public class DumpMkgmapCourseView {
    private static class ByteArrayChannel implements ImgChannel {
        private final byte[] data;
        private long position;

        ByteArrayChannel(byte[] data) {
            this.data = data;
        }

        protected int physicalPosition(long logicalPosition) {
            return (int) logicalPosition;
        }

        public int read(ByteBuffer dst) {
            if (position >= data.length) return -1;
            int start = (int) position;
            int n = Math.min(dst.remaining(), data.length - start);
            for (int i = 0; i < n; i++) {
                int physical = physicalPosition(position + i);
                dst.put(physical >= 0 && physical < data.length ? data[physical] : 0);
            }
            position += n;
            return n;
        }

        public int write(ByteBuffer src) {
            throw new UnsupportedOperationException("read only");
        }

        public boolean isOpen() {
            return true;
        }

        public void close() throws IOException {
        }

        public long position() {
            return position;
        }

        public void position(long pos) {
            position = pos;
        }
    }

    private static final class GmpRgnChannel extends ByteArrayChannel {
        private final int rgnOffset;
        private final int headerLength;

        GmpRgnChannel(byte[] data, int rgnOffset) {
            super(data);
            this.rgnOffset = rgnOffset;
            this.headerLength = u16(data, rgnOffset);
        }

        protected int physicalPosition(long logicalPosition) {
            if (logicalPosition < headerLength) return rgnOffset + (int) logicalPosition;
            return (int) logicalPosition;
        }
    }

    private static int u16(byte[] data, int offset) {
        return (data[offset] & 0xff) | ((data[offset + 1] & 0xff) << 8);
    }

    private static int u32(byte[] data, int offset) {
        return (data[offset] & 0xff)
                | ((data[offset + 1] & 0xff) << 8)
                | ((data[offset + 2] & 0xff) << 16)
                | ((data[offset + 3] & 0xff) << 24);
    }

    private static boolean hasMagic(byte[] data, int offset, String magic) {
        if (offset + magic.length() > data.length) return false;
        for (int i = 0; i < magic.length(); i++) {
            if ((data[offset + i] & 0xff) != magic.charAt(i)) return false;
        }
        return true;
    }

    private static byte[] extractGmp(byte[] data) {
        if (hasMagic(data, 2, "GARMIN GMP")) return data;

        int entry = 0x1200;
        int size = u32(data, entry + 12);
        byte[] out = new byte[size];
        int written = 0;
        for (int i = 0; i < 240 && written < size; i++) {
            int block = u16(data, entry + 0x20 + i * 2);
            if (block == 0 || block == 0xffff) continue;
            int src = block * 512;
            int n = Math.min(512, size - written);
            System.arraycopy(data, src, out, written, n);
            written += n;
        }
        return out;
    }

    private static String labelText(Label label) {
        if (label == null) return "";
        try {
            String text = label.getText();
            return text == null ? "" : text.replace("\\", "\\\\").replace("\"", "\\\"");
        } catch (Throwable t) {
            return label.toString().replace("\\", "\\\\").replace("\"", "\\\"");
        }
    }

    private static void count(Map<String, Integer> counts, String key) {
        Integer old = counts.get(key);
        counts.put(key, old == null ? 1 : old + 1);
    }

    private static void printPoint(Point point) {
        Coord coord = point.getLocation();
        System.out.printf(
                "{\"kind\":\"point\",\"type\":%d,\"typeHex\":\"0x%06x\",\"lon\":%.8f,\"lat\":%.8f,\"label\":\"%s\"}%n",
                point.getType(),
                point.getType(),
                Utils.toDegrees(coord.getLongitude()),
                Utils.toDegrees(coord.getLatitude()),
                labelText(point.getLabel()));
    }

    private static void printPoly(String kind, Polyline polyline) {
        System.out.printf(
                "{\"kind\":\"%s\",\"type\":%d,\"typeHex\":\"0x%06x\",\"n\":%d,\"label\":\"%s\",\"coords\":[",
                kind,
                polyline.getType(),
                polyline.getType(),
                polyline.getPoints().size(),
                labelText(polyline.getLabel()));
        List<Coord> coords = polyline.getPoints();
        for (int i = 0; i < coords.size(); i++) {
            Coord coord = coords.get(i);
            if (i > 0) System.out.print(",");
            System.out.printf("[%.8f,%.8f]", Utils.toDegrees(coord.getLongitude()), Utils.toDegrees(coord.getLatitude()));
        }
        System.out.println("]}");
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.err.println("usage: DumpMkgmapCourseView <file.img>");
            System.exit(2);
        }

        byte[] gmp = extractGmp(Files.readAllBytes(Paths.get(args[0])));
        int treOffset = u32(gmp, 0x19);
        int rgnOffset = u32(gmp, 0x1d);
        int lblOffset = u32(gmp, 0x21);
        System.err.printf("gmp bytes=%d tre=%d rgn=%d lbl=%d%n", gmp.length, treOffset, rgnOffset, lblOffset);

        Map<String, Integer> counts = new TreeMap<>();
        TREFileReader treFile = new TREFileReader(new ByteArrayChannel(gmp), treOffset);
        LBLFileReader lblFile = new LBLFileReader(new ByteArrayChannel(gmp), true, lblOffset);
        RGNFileReader rgnFile = new RGNFileReader(new GmpRgnChannel(gmp, rgnOffset));
        rgnFile.setLblFile(lblFile);

        Area bounds = treFile.getBounds();
        try {
            System.err.printf(
                    "bounds lon=[%.8f,%.8f] lat=[%.8f,%.8f]%n",
                    Utils.toDegrees(bounds.getMinLong()),
                    Utils.toDegrees(bounds.getMaxLong()),
                    Utils.toDegrees(bounds.getMinLat()),
                    Utils.toDegrees(bounds.getMaxLat()));

            for (Zoom zoom : treFile.getMapLevels()) {
                int level = zoom.getLevel();
                int polygonsAtLevel = 0;
                int linesAtLevel = 0;
                int pointsAtLevel = 0;

                for (Subdivision subdivision : treFile.subdivForLevel(level)) {
                    List<Polygon> polygons = rgnFile.shapesForSubdiv(subdivision, true);
                    List<Polyline> lines = rgnFile.linesForSubdiv(subdivision);
                    List<Point> points = rgnFile.pointsForSubdiv(subdivision, true);
                    polygonsAtLevel += polygons.size();
                    linesAtLevel += lines.size();
                    pointsAtLevel += points.size();

                    for (Polygon polygon : polygons) {
                        count(counts, String.format("polygon:0x%06x", polygon.getType()));
                        printPoly("polygon", polygon);
                    }
                    for (Polyline line : lines) {
                        count(counts, String.format("line:0x%06x", line.getType()));
                        printPoly("line", line);
                    }
                    for (Point point : points) {
                        count(counts, String.format("point:0x%06x", point.getType()));
                        printPoint(point);
                    }
                }
                System.err.printf(
                        "level=%d resolution=%d polygons=%d lines=%d points=%d%n",
                        level, zoom.getResolution(), polygonsAtLevel, linesAtLevel, pointsAtLevel);
            }
        } finally {
            treFile.close();
            lblFile.close();
            rgnFile.close();
        }

        for (Map.Entry<String, Integer> entry : counts.entrySet()) {
            System.err.printf("count %s %d%n", entry.getKey(), entry.getValue());
        }
    }
}
