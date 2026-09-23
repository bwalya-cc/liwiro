// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.modules;

import verun.runtime.evaluator.BuiltinFunction;

import java.lang.management.ManagementFactory;
import java.lang.management.ThreadMXBean;
import java.time.DateTimeException;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.TextStyle;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

public final class TimeDate {
    private static final Locale LOCALE = Locale.ENGLISH;

    private TimeDate() {
    }

    public static double time() {
        Instant now = Instant.now();
        return now.getEpochSecond() + (now.getNano() / 1_000_000_000.0d);
    }

    public static long timeNs() {
        Instant now = Instant.now();
        return now.getEpochSecond() * 1_000_000_000L + now.getNano();
    }

    public static double perfCounter() {
        return System.nanoTime() / 1_000_000_000.0d;
    }

    public static double monotonic() {
        return perfCounter();
    }

    public static double processTime() {
        ThreadMXBean bean = ManagementFactory.getThreadMXBean();
        if (bean.isCurrentThreadCpuTimeSupported()) {
            return bean.getCurrentThreadCpuTime() / 1_000_000_000.0d;
        }
        return 0.0d;
    }

    public static Object sleep(Object secondsValue) {
        double seconds = asDouble(secondsValue, 0.0d);
        if (seconds < 0) {
            throw new RuntimeException("time.sleep expects non-negative seconds");
        }
        long millis = (long) (seconds * 1000.0d);
        int nanos = (int) Math.round((seconds * 1_000_000_000.0d) - (millis * 1_000_000.0d));
        if (nanos < 0) {
            nanos = 0;
        }
        if (nanos > 999_999) {
            millis += nanos / 1_000_000;
            nanos = nanos % 1_000_000;
        }
        try {
            Thread.sleep(millis, nanos);
            return null;
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new RuntimeException("time.sleep interrupted");
        }
    }

    public static Map<String, Object> localtime(Object timestampMaybeNull) {
        Instant instant = instantFromMaybeTimestamp(timestampMaybeNull);
        return toTimeStruct(instant.atZone(ZoneId.systemDefault()));
    }

    public static Map<String, Object> gmtime(Object timestampMaybeNull) {
        Instant instant = instantFromMaybeTimestamp(timestampMaybeNull);
        return toTimeStruct(instant.atZone(ZoneOffset.UTC));
    }

    public static String strftime(String format, Object timeStruct) {
        if (!(timeStruct instanceof Map<?, ?>)) {
            throw new RuntimeException("time.strftime expects a time struct map");
        }
        ZonedDateTime zdt = structToZonedDateTime((Map<?, ?>) timeStruct);
        return formatStrftime(zdt, format == null ? "%a %b %d %H:%M:%S %Y" : format);
    }

    public static String ctime(Object timestampMaybeNull, Object formatMaybeNull, Object customPatternMaybeNull) {
        Instant instant = instantFromMaybeTimestamp(timestampMaybeNull);
        ZonedDateTime zdt = instant.atZone(ZoneId.systemDefault());

        String requested = formatMaybeNull == null ? "default" : String.valueOf(formatMaybeNull).trim();
        if (requested.isEmpty()) {
            requested = "default";
        }
        String lower = requested.toLowerCase(LOCALE);

        switch (lower) {
            case "default":
                return formatStrftime(zdt, "%a %b %d %H:%M:%S %Y");
            case "iso":
                return DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss", LOCALE).format(zdt);
            case "full":
                return DateTimeFormatter.ofPattern("d MMMM yyyy, h:mm a", LOCALE).format(zdt);
            case "custom":
                if (customPatternMaybeNull == null) {
                    return formatStrftime(zdt, "%a %b %d %H:%M:%S %Y");
                }
                return formatStrftime(zdt, String.valueOf(customPatternMaybeNull));
            default:
                return formatStrftime(zdt, requested);
        }
    }

    public static Map<String, Object> datetimeNow() {
        return datetimeFromZonedDateTime(ZonedDateTime.now());
    }

    public static Map<String, Object> datetimeFromTimestamp(Object value) {
        return datetimeFromZonedDateTime(instantFromTimestamp(value).atZone(ZoneId.systemDefault()));
    }

    public static Map<String, Object> dateToday() {
        return dateFromLocalDate(LocalDate.now());
    }

    public static Map<String, Object> dateFromTimestamp(Object value) {
        return dateFromLocalDate(instantFromTimestamp(value).atZone(ZoneId.systemDefault()).toLocalDate());
    }

    public static Map<String, Object> timeFromComponents(List<Object> args) {
        int hour = args.size() > 0 ? asInt(args.get(0), 0) : 0;
        int minute = args.size() > 1 ? asInt(args.get(1), 0) : 0;
        int second = args.size() > 2 ? asInt(args.get(2), 0) : 0;
        int micro = args.size() > 3 ? asInt(args.get(3), 0) : 0;

        if (hour < 0 || hour > 23) {
            throw new RuntimeException("datetime.time.from_components hour must be 0..23");
        }
        if (minute < 0 || minute > 59) {
            throw new RuntimeException("datetime.time.from_components minute must be 0..59");
        }
        if (second < 0 || second > 59) {
            throw new RuntimeException("datetime.time.from_components second must be 0..59");
        }
        if (micro < 0 || micro > 999_999) {
            throw new RuntimeException("datetime.time.from_components microsecond must be 0..999999");
        }

        LocalTime localTime = LocalTime.of(hour, minute, second, micro * 1000);
        return timeObject(localTime);
    }

    public static Map<String, Object> timedeltaFrom(Object raw) {
        if (raw instanceof Map<?, ?>) {
            Map<?, ?> map = (Map<?, ?>) raw;
            double days = asDouble(map.get("days"), 0.0d);
            double hours = asDouble(map.get("hours"), 0.0d);
            double minutes = asDouble(map.get("minutes"), 0.0d);
            double seconds = asDouble(map.get("seconds"), 0.0d);
            return timedeltaFromParts(days, hours, minutes, seconds);
        }
        if (raw instanceof List<?>) {
            List<?> list = (List<?>) raw;
            double days = list.size() > 0 ? asDouble(list.get(0), 0.0d) : 0.0d;
            double hours = list.size() > 1 ? asDouble(list.get(1), 0.0d) : 0.0d;
            double minutes = list.size() > 2 ? asDouble(list.get(2), 0.0d) : 0.0d;
            double seconds = list.size() > 3 ? asDouble(list.get(3), 0.0d) : 0.0d;
            return timedeltaFromParts(days, hours, minutes, seconds);
        }
        if (raw instanceof Number) {
            return timedeltaFromParts(0, 0, 0, ((Number) raw).doubleValue());
        }
        if (raw == null) {
            return timedeltaFromParts(0, 0, 0, 0);
        }
        throw new RuntimeException("datetime.timedelta expects map, list, number, or null");
    }

    public static Map<String, Object> timezoneFrom(Object raw) {
        int offsetSeconds;
        if (raw instanceof Number) {
            offsetSeconds = ((Number) raw).intValue();
        } else {
            String text = String.valueOf(raw == null ? "" : raw).trim();
            if (text.isEmpty()) {
                offsetSeconds = 0;
            } else if (text.matches("^[+-]\\d{2}:?\\d{2}$")) {
                boolean negative = text.startsWith("-");
                String clean = text.replace("+", "").replace("-", "").replace(":", "");
                int hh = Integer.parseInt(clean.substring(0, 2));
                int mm = Integer.parseInt(clean.substring(2, 4));
                offsetSeconds = (hh * 3600) + (mm * 60);
                if (negative) {
                    offsetSeconds *= -1;
                }
            } else {
                throw new RuntimeException("datetime.timezone expects offset seconds or +HH:MM string");
            }
        }

        ZoneOffset offset = ZoneOffset.ofTotalSeconds(offsetSeconds);
        Map<String, Object> zone = new LinkedHashMap<>();
        zone.put("__vi_type", "timezone");
        zone.put("offset_seconds", offsetSeconds);
        zone.put("name", offset.getId());
        return zone;
    }

    public static String timezoneIsoformat(Map<?, ?> timezoneValue) {
        if (timezoneValue == null) {
            return "+00:00";
        }
        int total = asInt(timezoneValue.get("offset_seconds"), 0);
        int abs = Math.abs(total);
        int hh = abs / 3600;
        int mm = (abs % 3600) / 60;
        return (total >= 0 ? "+" : "-") + pad(hh, 2) + ":" + pad(mm, 2);
    }

    public static String timezoneHumanReadable(Map<?, ?> timezoneValue) {
        String iso = timezoneIsoformat(timezoneValue);
        Object name = timezoneValue == null ? null : timezoneValue.get("name");
        String label = name == null ? "" : String.valueOf(name);
        if (label.isEmpty() || iso.equals(label)) {
            return iso;
        }
        return label + " (" + iso + ")";
    }

    public static Object tryApplyOperator(String operator, Object left, Object right) {
        if (!(left instanceof Map<?, ?>) && !(right instanceof Map<?, ?>)) {
            return null;
        }
        String leftType = viType(left);
        String rightType = viType(right);

        if ("+".equals(operator)) {
            if ("datetime".equals(leftType) && "timedelta".equals(rightType)) {
                return addDatetimeAndTimedelta((Map<String, Object>) left, (Map<String, Object>) right);
            }
            if ("timedelta".equals(leftType) && "datetime".equals(rightType)) {
                return addDatetimeAndTimedelta((Map<String, Object>) right, (Map<String, Object>) left);
            }
            if ("timedelta".equals(leftType) && "timedelta".equals(rightType)) {
                double total = timedeltaTotalSeconds((Map<String, Object>) left) + timedeltaTotalSeconds((Map<String, Object>) right);
                return timedeltaFromParts(0, 0, 0, total);
            }
        }

        if ("-".equals(operator)) {
            if ("datetime".equals(leftType) && "timedelta".equals(rightType)) {
                return subtractTimedeltaFromDatetime((Map<String, Object>) left, (Map<String, Object>) right);
            }
            if ("datetime".equals(leftType) && "datetime".equals(rightType)) {
                double total = timestampSeconds((Map<String, Object>) left) - timestampSeconds((Map<String, Object>) right);
                return timedeltaFromParts(0, 0, 0, total);
            }
            if ("timedelta".equals(leftType) && "timedelta".equals(rightType)) {
                double total = timedeltaTotalSeconds((Map<String, Object>) left) - timedeltaTotalSeconds((Map<String, Object>) right);
                return timedeltaFromParts(0, 0, 0, total);
            }
        }

        return null;
    }

    public static String viType(Object value) {
        if (!(value instanceof Map<?, ?>)) {
            return null;
        }
        Object marker = ((Map<?, ?>) value).get("__vi_type");
        if (!(marker instanceof String)) {
            return null;
        }
        return String.valueOf(marker);
    }

    public static String versaType(Object value) {
        return viType(value);
    }

    @SuppressWarnings("unchecked")
    public static Map<String, Object> addDatetimeAndTimedelta(Map<String, Object> dateTimeValue, Map<String, Object> deltaValue) {
        double seconds = timestampSeconds(dateTimeValue) + timedeltaTotalSeconds(deltaValue);
        return datetimeFromTimestampWithZone(seconds, zoneFromDateTime(dateTimeValue));
    }

    @SuppressWarnings("unchecked")
    public static Map<String, Object> subtractTimedeltaFromDatetime(Map<String, Object> dateTimeValue, Map<String, Object> deltaValue) {
        double seconds = timestampSeconds(dateTimeValue) - timedeltaTotalSeconds(deltaValue);
        return datetimeFromTimestampWithZone(seconds, zoneFromDateTime(dateTimeValue));
    }

    public static Object subtractDateTimeValues(Map<String, Object> left, Object right) {
        String rightType = viType(right);
        if ("timedelta".equals(rightType)) {
            return subtractTimedeltaFromDatetime(left, (Map<String, Object>) right);
        }
        if ("datetime".equals(rightType)) {
            double diff = timestampSeconds(left) - timestampSeconds((Map<String, Object>) right);
            return timedeltaFromParts(0, 0, 0, diff);
        }
        throw new RuntimeException("datetime.subtract expects timedelta or datetime");
    }

    public static String datetimeIsoformat(Map<String, Object> dateTimeValue) {
        return DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss", LOCALE).format(dateTimeToZoned(dateTimeValue));
    }

    public static String datetimeHumanReadable(Map<String, Object> dateTimeValue, Object formatMaybeNull, Object customMaybeNull) {
        ZonedDateTime zdt = dateTimeToZoned(dateTimeValue);
        String format = formatMaybeNull == null ? "default" : String.valueOf(formatMaybeNull).trim();
        if (format.isEmpty()) {
            format = "default";
        }
        String lower = format.toLowerCase(LOCALE);
        if ("default".equals(lower)) {
            return formatStrftime(zdt, "%a %b %d %H:%M:%S %Y");
        }
        if ("iso".equals(lower)) {
            return datetimeIsoformat(dateTimeValue);
        }
        if ("full".equals(lower)) {
            return DateTimeFormatter.ofPattern("d MMMM yyyy, h:mm a", LOCALE).format(zdt);
        }
        if ("custom".equals(lower)) {
            String custom = customMaybeNull == null ? "%a %b %d %H:%M:%S %Y" : String.valueOf(customMaybeNull);
            return formatStrftime(zdt, custom);
        }
        return formatStrftime(zdt, format);
    }

    public static String dateIsoformat(Map<String, Object> dateValue) {
        LocalDate date = LocalDate.of(asInt(dateValue.get("year"), 1970), asInt(dateValue.get("month"), 1), asInt(dateValue.get("day"), 1));
        return DateTimeFormatter.ISO_LOCAL_DATE.format(date);
    }

    public static String dateHumanReadable(Map<String, Object> dateValue, Object formatMaybeNull, Object customMaybeNull) {
        LocalDate date = LocalDate.of(asInt(dateValue.get("year"), 1970), asInt(dateValue.get("month"), 1), asInt(dateValue.get("day"), 1));
        String format = formatMaybeNull == null ? "default" : String.valueOf(formatMaybeNull).trim();
        if (format.isEmpty()) {
            format = "default";
        }
        String lower = format.toLowerCase(LOCALE);
        if ("iso".equals(lower)) {
            return dateIsoformat(dateValue);
        }
        if ("full".equals(lower)) {
            return DateTimeFormatter.ofPattern("d MMMM yyyy", LOCALE).format(date);
        }
        if ("default".equals(lower)) {
            return DateTimeFormatter.ofPattern("d MMM yyyy", LOCALE).format(date);
        }
        if ("custom".equals(lower)) {
            String custom = customMaybeNull == null ? "%d %b %Y" : String.valueOf(customMaybeNull);
            ZonedDateTime zdt = date.atStartOfDay(ZoneId.systemDefault());
            return formatStrftime(zdt, custom);
        }
        ZonedDateTime zdt = date.atStartOfDay(ZoneId.systemDefault());
        return formatStrftime(zdt, format);
    }

    public static String timeIsoformat(Map<String, Object> timeValue) {
        LocalTime localTime = localTimeFromMap(timeValue);
        return DateTimeFormatter.ofPattern("HH:mm:ss", LOCALE).format(localTime);
    }

    public static String timeHumanReadable(Map<String, Object> timeValue, Object formatMaybeNull, Object customMaybeNull) {
        LocalTime localTime = localTimeFromMap(timeValue);
        String format = formatMaybeNull == null ? "default" : String.valueOf(formatMaybeNull).trim();
        if (format.isEmpty()) {
            format = "default";
        }
        String lower = format.toLowerCase(LOCALE);
        ZonedDateTime zdt = ZonedDateTime.of(LocalDate.of(1970, 1, 1), localTime, ZoneId.systemDefault());
        if ("iso".equals(lower)) {
            return timeIsoformat(timeValue);
        }
        if ("full".equals(lower) || "default".equals(lower)) {
            return DateTimeFormatter.ofPattern("h:mm a", LOCALE).format(localTime);
        }
        if ("custom".equals(lower)) {
            String custom = customMaybeNull == null ? "%I:%M:%S %p" : String.valueOf(customMaybeNull);
            return formatStrftime(zdt, custom);
        }
        return formatStrftime(zdt, format);
    }

    public static double timedeltaTotalSeconds(Map<String, Object> deltaValue) {
        return asDouble(deltaValue.get("total_seconds"), 0.0d);
    }

    public static String timedeltaHumanReadable(Map<String, Object> deltaValue) {
        double total = timedeltaTotalSeconds(deltaValue);
        double abs = Math.abs(total);
        long days = (long) (abs / 86400);
        abs -= days * 86400;
        long hours = (long) (abs / 3600);
        abs -= hours * 3600;
        long minutes = (long) (abs / 60);
        abs -= minutes * 60;
        long seconds = Math.round(abs);
        String sign = total < 0 ? "-" : "";
        return sign + days + "d " + hours + "h " + minutes + "m " + seconds + "s";
    }

    private static Map<String, Object> datetimeFromTimestampWithZone(double timestampSeconds, ZoneId zone) {
        long epochSeconds = (long) Math.floor(timestampSeconds);
        double fraction = timestampSeconds - epochSeconds;
        long nanos = Math.round(fraction * 1_000_000_000.0d);
        if (nanos >= 1_000_000_000L) {
            epochSeconds += 1;
            nanos = 0;
        }
        Instant instant = Instant.ofEpochSecond(epochSeconds, nanos);
        return datetimeFromZonedDateTime(instant.atZone(zone));
    }

    private static ZoneId zoneFromDateTime(Map<String, Object> dateTimeValue) {
        Object zoneObj = dateTimeValue.get("timezone");
        if (zoneObj == null) {
            return ZoneId.systemDefault();
        }
        String text = String.valueOf(zoneObj);
        try {
            return ZoneId.of(text);
        } catch (DateTimeException e) {
            try {
                return ZoneOffset.of(text);
            } catch (DateTimeException ignored) {
                return ZoneId.systemDefault();
            }
        }
    }

    private static ZonedDateTime dateTimeToZoned(Map<String, Object> dateTimeValue) {
        double timestamp = timestampSeconds(dateTimeValue);
        return instantFromTimestamp(timestamp).atZone(zoneFromDateTime(dateTimeValue));
    }

    private static double timestampSeconds(Map<String, Object> dateTimeValue) {
        return asDouble(dateTimeValue.get("timestamp"), time());
    }

    private static Map<String, Object> datetimeFromZonedDateTime(ZonedDateTime zdt) {
        Map<String, Object> value = new LinkedHashMap<>();
        value.put("__vi_type", "datetime");
        value.put("year", zdt.getYear());
        value.put("month", zdt.getMonthValue());
        value.put("day", zdt.getDayOfMonth());
        value.put("hour", zdt.getHour());
        value.put("minute", zdt.getMinute());
        value.put("second", zdt.getSecond());
        value.put("microsecond", zdt.getNano() / 1000);
        value.put("weekday", zdt.getDayOfWeek().getValue() - 1);
        value.put("yearday", zdt.getDayOfYear());
        value.put("timezone", zdt.getOffset().getId());
        value.put("timestamp", zdt.toInstant().getEpochSecond() + (zdt.getNano() / 1_000_000_000.0d));

        value.put("isoformat", new BuiltinFunction(args -> datetimeIsoformat(value)));
        value.put("human_readable", new BuiltinFunction(args -> {
            Object format = args.size() > 0 ? args.get(0) : "default";
            Object custom = args.size() > 1 ? args.get(1) : null;
            return datetimeHumanReadable(value, format, custom);
        }));
        value.put("human", new BuiltinFunction(args -> {
            Object format = args.size() > 0 ? args.get(0) : "default";
            Object custom = args.size() > 1 ? args.get(1) : null;
            return datetimeHumanReadable(value, format, custom);
        }));
        value.put("add", new BuiltinFunction(args -> {
            if (args.isEmpty()) {
                throw new RuntimeException("datetime.add expects timedelta");
            }
            if (!(args.get(0) instanceof Map<?, ?>) || !"timedelta".equals(viType(args.get(0)))) {
                throw new RuntimeException("datetime.add expects timedelta");
            }
            return addDatetimeAndTimedelta(value, (Map<String, Object>) args.get(0));
        }));
        value.put("subtract", new BuiltinFunction(args -> {
            if (args.isEmpty()) {
                throw new RuntimeException("datetime.subtract expects timedelta or datetime");
            }
            return subtractDateTimeValues(value, args.get(0));
        }));
        value.put("diff", new BuiltinFunction(args -> {
            if (args.isEmpty() || !(args.get(0) instanceof Map<?, ?>) || !"datetime".equals(viType(args.get(0)))) {
                throw new RuntimeException("datetime.diff expects datetime");
            }
            double diff = timestampSeconds(value) - timestampSeconds((Map<String, Object>) args.get(0));
            return timedeltaFromParts(0, 0, 0, diff);
        }));

        return value;
    }

    private static Map<String, Object> dateFromLocalDate(LocalDate date) {
        Map<String, Object> value = new LinkedHashMap<>();
        value.put("__vi_type", "date");
        value.put("year", date.getYear());
        value.put("month", date.getMonthValue());
        value.put("day", date.getDayOfMonth());
        value.put("weekday", date.getDayOfWeek().getValue() - 1);
        value.put("yearday", date.getDayOfYear());

        value.put("isoformat", new BuiltinFunction(args -> dateIsoformat(value)));
        value.put("human_readable", new BuiltinFunction(args -> {
            Object format = args.size() > 0 ? args.get(0) : "default";
            Object custom = args.size() > 1 ? args.get(1) : null;
            return dateHumanReadable(value, format, custom);
        }));
        value.put("human", new BuiltinFunction(args -> {
            Object format = args.size() > 0 ? args.get(0) : "default";
            Object custom = args.size() > 1 ? args.get(1) : null;
            return dateHumanReadable(value, format, custom);
        }));

        return value;
    }

    private static Map<String, Object> timeObject(LocalTime localTime) {
        Map<String, Object> value = new LinkedHashMap<>();
        value.put("__vi_type", "time");
        value.put("hour", localTime.getHour());
        value.put("minute", localTime.getMinute());
        value.put("second", localTime.getSecond());
        value.put("microsecond", localTime.getNano() / 1000);

        value.put("isoformat", new BuiltinFunction(args -> timeIsoformat(value)));
        value.put("human_readable", new BuiltinFunction(args -> {
            Object format = args.size() > 0 ? args.get(0) : "default";
            Object custom = args.size() > 1 ? args.get(1) : null;
            return timeHumanReadable(value, format, custom);
        }));
        value.put("human", new BuiltinFunction(args -> {
            Object format = args.size() > 0 ? args.get(0) : "default";
            Object custom = args.size() > 1 ? args.get(1) : null;
            return timeHumanReadable(value, format, custom);
        }));

        return value;
    }

    private static LocalTime localTimeFromMap(Map<String, Object> timeValue) {
        int hour = asInt(timeValue.get("hour"), 0);
        int minute = asInt(timeValue.get("minute"), 0);
        int second = asInt(timeValue.get("second"), 0);
        int micro = asInt(timeValue.get("microsecond"), 0);
        return LocalTime.of(hour, minute, second, micro * 1000);
    }

    private static Map<String, Object> timedeltaFromParts(double days, double hours, double minutes, double seconds) {
        double totalSeconds = seconds + (minutes * 60.0d) + (hours * 3600.0d) + (days * 86400.0d);
        double abs = Math.abs(totalSeconds);
        long wholeDays = (long) (abs / 86400);
        abs -= wholeDays * 86400;
        long wholeHours = (long) (abs / 3600);
        abs -= wholeHours * 3600;
        long wholeMinutes = (long) (abs / 60);
        abs -= wholeMinutes * 60;

        Map<String, Object> value = new LinkedHashMap<>();
        value.put("__vi_type", "timedelta");
        value.put("days", totalSeconds < 0 ? -wholeDays : wholeDays);
        value.put("hours", wholeHours);
        value.put("minutes", wholeMinutes);
        value.put("seconds", abs);
        value.put("total_seconds", totalSeconds);

        value.put("total_seconds_fn", new BuiltinFunction(args -> timedeltaTotalSeconds(value)));
        value.put("total_seconds", totalSeconds);
        value.put("human_readable", new BuiltinFunction(args -> timedeltaHumanReadable(value)));
        value.put("human", new BuiltinFunction(args -> timedeltaHumanReadable(value)));
        value.put("total_seconds_value", totalSeconds);
        value.put("total_seconds_method", new BuiltinFunction(args -> timedeltaTotalSeconds(value)));

        return value;
    }

    private static Map<String, Object> toTimeStruct(ZonedDateTime zdt) {
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("__vi_type", "time_struct");
        out.put("year", zdt.getYear());
        out.put("month", zdt.getMonthValue());
        out.put("day", zdt.getDayOfMonth());
        out.put("hour", zdt.getHour());
        out.put("minute", zdt.getMinute());
        out.put("second", zdt.getSecond());
        out.put("microsecond", zdt.getNano() / 1000);
        out.put("weekday", zdt.getDayOfWeek().getValue() - 1);
        out.put("yearday", zdt.getDayOfYear());
        out.put("is_dst", false);
        out.put("utc_offset_seconds", zdt.getOffset().getTotalSeconds());
        out.put("zone", zdt.getZone().getId());
        out.put("epoch", zdt.toInstant().getEpochSecond() + (zdt.getNano() / 1_000_000_000.0d));
        return out;
    }

    private static ZonedDateTime structToZonedDateTime(Map<?, ?> struct) {
        int year = asInt(struct.get("year"), 1970);
        int month = asInt(struct.get("month"), 1);
        int day = asInt(struct.get("day"), 1);
        int hour = asInt(struct.get("hour"), 0);
        int minute = asInt(struct.get("minute"), 0);
        int second = asInt(struct.get("second"), 0);
        int micro = asInt(struct.get("microsecond"), 0);

        ZoneId zone = ZoneId.systemDefault();
        Object zoneRaw = struct.get("zone");
        if (zoneRaw != null) {
            String zoneText = String.valueOf(zoneRaw);
            try {
                zone = ZoneId.of(zoneText);
            } catch (DateTimeException e) {
                try {
                    zone = ZoneOffset.of(zoneText);
                } catch (DateTimeException ignored) {
                    zone = ZoneId.systemDefault();
                }
            }
        } else if (struct.containsKey("utc_offset_seconds")) {
            zone = ZoneOffset.ofTotalSeconds(asInt(struct.get("utc_offset_seconds"), 0));
        }

        LocalDateTime ldt = LocalDateTime.of(year, month, day, hour, minute, second, micro * 1000);
        return ldt.atZone(zone);
    }

    private static String formatStrftime(ZonedDateTime zdt, String format) {
        StringBuilder out = new StringBuilder();
        for (int i = 0; i < format.length(); i++) {
            char ch = format.charAt(i);
            if (ch != '%') {
                out.append(ch);
                continue;
            }
            if (i + 1 >= format.length()) {
                out.append('%');
                break;
            }
            char token = format.charAt(++i);
            switch (token) {
                case '%':
                    out.append('%');
                    break;
                case 'Y':
                    out.append(pad(zdt.getYear(), 4));
                    break;
                case 'y':
                    out.append(pad(zdt.getYear() % 100, 2));
                    break;
                case 'm':
                    out.append(pad(zdt.getMonthValue(), 2));
                    break;
                case 'd':
                    out.append(pad(zdt.getDayOfMonth(), 2));
                    break;
                case 'H':
                    out.append(pad(zdt.getHour(), 2));
                    break;
                case 'M':
                    out.append(pad(zdt.getMinute(), 2));
                    break;
                case 'S':
                    out.append(pad(zdt.getSecond(), 2));
                    break;
                case 'I': {
                    int hour12 = zdt.getHour() % 12;
                    if (hour12 == 0) {
                        hour12 = 12;
                    }
                    out.append(pad(hour12, 2));
                    break;
                }
                case 'p':
                    out.append(zdt.getHour() < 12 ? "AM" : "PM");
                    break;
                case 'a':
                    out.append(zdt.getDayOfWeek().getDisplayName(TextStyle.SHORT, LOCALE));
                    break;
                case 'A':
                    out.append(zdt.getDayOfWeek().getDisplayName(TextStyle.FULL, LOCALE));
                    break;
                case 'b':
                    out.append(zdt.getMonth().getDisplayName(TextStyle.SHORT, LOCALE));
                    break;
                case 'B':
                    out.append(zdt.getMonth().getDisplayName(TextStyle.FULL, LOCALE));
                    break;
                case 'j':
                    out.append(pad(zdt.getDayOfYear(), 3));
                    break;
                case 'w':
                    out.append(zdt.getDayOfWeek().getValue() % 7);
                    break;
                case 'z': {
                    int total = zdt.getOffset().getTotalSeconds();
                    int abs = Math.abs(total);
                    int hh = abs / 3600;
                    int mm = (abs % 3600) / 60;
                    out.append(total >= 0 ? "+" : "-");
                    out.append(pad(hh, 2)).append(pad(mm, 2));
                    break;
                }
                case 'Z':
                    out.append(zdt.getZone().getId());
                    break;
                case 'f':
                    out.append(pad(zdt.getNano() / 1000, 6));
                    break;
                case 'F':
                    out.append(formatStrftime(zdt, "%Y-%m-%d"));
                    break;
                case 'T':
                    out.append(formatStrftime(zdt, "%H:%M:%S"));
                    break;
                case 'R':
                    out.append(formatStrftime(zdt, "%H:%M"));
                    break;
                case 'D':
                    out.append(formatStrftime(zdt, "%m/%d/%y"));
                    break;
                case 'c':
                    out.append(formatStrftime(zdt, "%a %b %d %H:%M:%S %Y"));
                    break;
                case 'x':
                    out.append(formatStrftime(zdt, "%m/%d/%y"));
                    break;
                case 'X':
                    out.append(formatStrftime(zdt, "%H:%M:%S"));
                    break;
                default:
                    out.append('%').append(token);
            }
        }
        return out.toString();
    }

    private static String pad(long value, int width) {
        String raw = String.valueOf(Math.abs(value));
        StringBuilder out = new StringBuilder();
        if (value < 0) {
            out.append('-');
        }
        for (int i = raw.length(); i < width; i++) {
            out.append('0');
        }
        out.append(raw);
        return out.toString();
    }

    private static Instant instantFromMaybeTimestamp(Object value) {
        if (value == null) {
            return Instant.now();
        }
        return instantFromTimestamp(value);
    }

    private static Instant instantFromTimestamp(Object value) {
        double seconds = asDouble(value, 0.0d);
        long whole = (long) Math.floor(seconds);
        long nanos = Math.round((seconds - whole) * 1_000_000_000.0d);
        if (nanos >= 1_000_000_000L) {
            whole += 1;
            nanos = 0;
        }
        return Instant.ofEpochSecond(whole, nanos);
    }

    private static int asInt(Object value, int fallback) {
        if (value == null) {
            return fallback;
        }
        if (value instanceof Number) {
            return ((Number) value).intValue();
        }
        String text = String.valueOf(value).trim();
        if (text.isEmpty()) {
            return fallback;
        }
        return Integer.parseInt(text);
    }

    private static double asDouble(Object value, double fallback) {
        if (value == null) {
            return fallback;
        }
        if (value instanceof Number) {
            return ((Number) value).doubleValue();
        }
        String text = String.valueOf(value).trim();
        if (text.isEmpty()) {
            return fallback;
        }
        return Double.parseDouble(text);
    }
}
