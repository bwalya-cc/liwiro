// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.runtime.modules;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Random;

public final class RandomModule {
    private static final Random RNG = new Random();

    private RandomModule() {
    }

    public static synchronized void seed(Object seedValue) {
        long seed;
        if (seedValue == null) {
            seed = System.nanoTime();
        } else if (seedValue instanceof Number) {
            seed = ((Number) seedValue).longValue();
        } else {
            seed = String.valueOf(seedValue).hashCode();
        }
        RNG.setSeed(seed);
    }

    public static synchronized double random() {
        return RNG.nextDouble();
    }

    public static synchronized int randint(int minInclusive, int maxInclusive) {
        int low = Math.min(minInclusive, maxInclusive);
        int high = Math.max(minInclusive, maxInclusive);
        long span = (long) high - (long) low + 1L;
        if (span <= 0L) {
            throw new RuntimeException("random.randint range is too large");
        }
        return low + RNG.nextInt((int) span);
    }

    public static synchronized List<Integer> randints(int minInclusive, int maxInclusive, int count) {
        if (count < 0) {
            throw new RuntimeException("random.randints count must be >= 0");
        }
        List<Integer> out = new ArrayList<>();
        for (int i = 0; i < count; i++) {
            out.add(randint(minInclusive, maxInclusive));
        }
        return out;
    }

    public static synchronized int randrange(int start, int stop, Integer stepMaybeNull) {
        int step = stepMaybeNull == null ? 1 : stepMaybeNull;
        if (step == 0) {
            throw new RuntimeException("random.randrange step cannot be 0");
        }
        List<Integer> values = new ArrayList<>();
        if (step > 0) {
            for (int i = start; i < stop; i += step) {
                values.add(i);
            }
        } else {
            for (int i = start; i > stop; i += step) {
                values.add(i);
            }
        }
        if (values.isEmpty()) {
            throw new RuntimeException("random.randrange produced an empty range");
        }
        return values.get(RNG.nextInt(values.size()));
    }

    public static synchronized double uniform(double min, double max) {
        double low = Math.min(min, max);
        double high = Math.max(min, max);
        return low + (RNG.nextDouble() * (high - low));
    }

    public static synchronized Object choice(List<?> values) {
        if (values == null || values.isEmpty()) {
            throw new RuntimeException("random.choice expects a non-empty list");
        }
        return values.get(RNG.nextInt(values.size()));
    }

    public static synchronized List<Object> choices(List<?> values, int count) {
        if (values == null || values.isEmpty()) {
            throw new RuntimeException("random.choices expects a non-empty list");
        }
        if (count < 0) {
            throw new RuntimeException("random.choices count must be >= 0");
        }
        List<Object> out = new ArrayList<>();
        for (int i = 0; i < count; i++) {
            out.add(values.get(RNG.nextInt(values.size())));
        }
        return out;
    }

    public static synchronized void shuffle(List<Object> values) {
        if (values == null) {
            throw new RuntimeException("random.shuffle expects a list");
        }
        Collections.shuffle(values, RNG);
    }

    public static synchronized List<Object> sample(List<?> values, int count) {
        if (values == null) {
            throw new RuntimeException("random.sample expects a list");
        }
        if (count < 0 || count > values.size()) {
            throw new RuntimeException("random.sample count must be between 0 and list size");
        }
        List<Object> pool = new ArrayList<>(values);
        Collections.shuffle(pool, RNG);
        return new ArrayList<>(pool.subList(0, count));
    }

    public static synchronized boolean booleanValue() {
        return RNG.nextBoolean();
    }

    public static synchronized boolean chance(double probability) {
        if (probability < 0.0d || probability > 1.0d) {
            throw new RuntimeException("random.chance expects probability between 0 and 1");
        }
        return RNG.nextDouble() < probability;
    }
}
