"use client";

import { useEffect, useRef } from "react";

import { api } from "@/lib/api/client";

import { useSession } from "./session";

/** Adds this property to the signed-in user's history, if they keep one. */
export function RecordView({ propertyId }: { propertyId: string }) {
  const { me } = useSession();
  // Once per property: Strict Mode runs effects twice, and a session refresh re-runs this one.
  const recorded = useRef<string | null>(null);
  useEffect(() => {
    if (!me?.historyEnabled || recorded.current === propertyId) return;
    recorded.current = propertyId;
    api.recordView(propertyId).catch(() => {});
  }, [me?.historyEnabled, propertyId]);
  return null;
}
