"use client";

import { useEffect } from "react";

import { api } from "@/lib/api/client";

import { useSession } from "./session";

/** Adds this property to the signed-in user's history, if they keep one. */
export function RecordView({ propertyId }: { propertyId: string }) {
  const { me } = useSession();
  useEffect(() => {
    if (me?.historyEnabled) api.recordView(propertyId).catch(() => {});
  }, [me?.historyEnabled, propertyId]);
  return null;
}
