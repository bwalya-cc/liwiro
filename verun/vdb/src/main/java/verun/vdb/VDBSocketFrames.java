// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.vdb;

import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.EOFException;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;

public final class VDBSocketFrames {
    private static final int MAX_FRAME_BYTES = 64 * 1024 * 1024;

    private VDBSocketFrames() {
    }

    public static String readFrame(InputStream inputStream) throws IOException {
        DataInputStream input = new DataInputStream(inputStream);
        final int length;
        try {
            length = input.readInt();
        } catch (EOFException eof) {
            return null;
        }
        if (length < 0 || length > MAX_FRAME_BYTES) {
            throw new IOException("Invalid frame length: " + length);
        }
        byte[] payload = new byte[length];
        input.readFully(payload);
        return new String(payload, StandardCharsets.UTF_8);
    }

    public static void writeFrame(OutputStream outputStream, String payload) throws IOException {
        byte[] bytes = (payload == null ? "" : payload).getBytes(StandardCharsets.UTF_8);
        if (bytes.length > MAX_FRAME_BYTES) {
            throw new IOException("Frame too large: " + bytes.length);
        }
        DataOutputStream output = new DataOutputStream(outputStream);
        output.writeInt(bytes.length);
        output.write(bytes);
        output.flush();
    }
}
