// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.vdb;

public class VDBTransportResponse {
    private final int statusCode;
    private final String contentType;
    private final String body;

    public VDBTransportResponse(int statusCode, String contentType, String body) {
        this.statusCode = statusCode;
        this.contentType = contentType == null || contentType.trim().isEmpty()
                ? "application/json; charset=UTF-8"
                : contentType;
        this.body = body == null ? "" : body;
    }

    public int getStatusCode() {
        return statusCode;
    }

    public String getContentType() {
        return contentType;
    }

    public String getBody() {
        return body;
    }

    public static VDBTransportResponse json(int statusCode, String body) {
        return new VDBTransportResponse(statusCode, "application/json; charset=UTF-8", body);
    }

    public static VDBTransportResponse text(int statusCode, String body) {
        return new VDBTransportResponse(statusCode, "text/plain; charset=UTF-8", body);
    }
}
