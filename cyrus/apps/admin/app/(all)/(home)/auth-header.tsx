/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import Link from "next/link";

export function AuthHeader() {
  return (
    <div className="sticky top-0 flex w-full flex-shrink-0 items-center justify-between gap-6">
      <Link href="/" className="inline-flex items-center gap-2 text-primary">
        <span className="text-20 font-semibold tracking-tight">Cyrus</span>
      </Link>
    </div>
  );
}
