// Copyright (c) 2026 Bwalya Cameron Chishimba
// SPDX-License-Identifier: AGPL-3.0-only OR LicenseRef-Commercial

package verun.vdb;

public class ValidationException extends RuntimeException {
    public ValidationException(String message) {
        super(message);
    }
}