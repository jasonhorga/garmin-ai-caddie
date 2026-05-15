import org.free.garminimg.CoordUtils;
import org.free.garminimg.ImgFileBag;
import org.free.garminimg.ImgFilesBag;
import org.free.garminimg.Label;
import org.free.garminimg.MapListener;
import org.free.garminimg.ObjectKind;
import org.free.garminimg.SubDivision;

import java.io.File;
import java.util.Map;
import java.util.TreeMap;

public class DumpCourseView {
    private static class Listener implements MapListener {
        int points = 0;
        int lines = 0;
        int polygons = 0;
        final Map<String, Integer> counts = new TreeMap<String, Integer>();

        private void inc(String key) {
            Integer old = counts.get(key);
            counts.put(key, old == null ? 1 : old + 1);
        }

        private static String labelName(Label label) {
            if (label == null) return "";
            try {
                String name = label.getName();
                return name == null ? "" : name.replace("\\", "\\\\").replace("\"", "\\\"");
            } catch (Exception e) {
                return "LABEL_ERROR:" + e.getClass().getSimpleName();
            }
        }

        public void addPoint(int type, int subType, int longitude, int latitude, Label label, boolean indexed) {
            points++;
            inc(String.format("point:0x%02x:0x%02x", type, subType));
            System.out.printf(
                    "{\"kind\":\"point\",\"type\":%d,\"subType\":%d,\"lon\":%.8f,\"lat\":%.8f,\"label\":\"%s\",\"indexed\":%s}%n",
                    type, subType, CoordUtils.toWGS84(longitude), CoordUtils.toWGS84(latitude), labelName(label), indexed);
        }

        public void addPoly(int type, int[] longitudes, int[] latitudes, int nbPoints, Label label, boolean line) {
            if (line) lines++;
            else polygons++;
            inc(String.format("%s:0x%02x", line ? "line" : "polygon", type));
            System.out.printf(
                    "{\"kind\":\"%s\",\"type\":%d,\"n\":%d,\"label\":\"%s\",\"coords\":[",
                    line ? "line" : "polygon", type, nbPoints, labelName(label));
            for (int i = 0; i < nbPoints; i++) {
                if (i > 0) System.out.print(",");
                System.out.printf("[%.8f,%.8f]", CoordUtils.toWGS84(longitudes[i]), CoordUtils.toWGS84(latitudes[i]));
            }
            System.out.println("]}");
        }

        public void startMap(ImgFileBag file) {
            System.err.println("startMap " + file.getFile());
        }

        public void startSubDivision(SubDivision subDivision) {
        }

        public void finishPainting() {
            System.err.printf("summary points=%d lines=%d polygons=%d%n", points, lines, polygons);
            for (Map.Entry<String, Integer> entry : counts.entrySet()) {
                System.err.printf("count %s %d%n", entry.getKey(), entry.getValue());
            }
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.err.println("usage: DumpCourseView <file.img>");
            System.exit(2);
        }
        ImgFilesBag maps = new ImgFilesBag();
        maps.addFile(new File(args[0]));
        System.err.printf(
                "bounds lon=[%.8f,%.8f] lat=[%.8f,%.8f]%n",
                CoordUtils.toWGS84(maps.getMinLongitude()),
                CoordUtils.toWGS84(maps.getMaxLongitude()),
                CoordUtils.toWGS84(maps.getMinLatitude()),
                CoordUtils.toWGS84(maps.getMaxLatitude()));
        maps.readMap(
                maps.getMinLongitude(),
                maps.getMaxLongitude(),
                maps.getMinLatitude(),
                maps.getMaxLatitude(),
                -1,
                ObjectKind.ALL,
                null,
                new Listener());
    }
}
