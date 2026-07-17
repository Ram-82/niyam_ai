"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { getAccessToken } from "@/lib/auth";

export default function IndexPage() {
  const router = useRouter();
  useEffect(() => {
    router.replace(getAccessToken() ? "/command-center" : "/login");
  }, [router]);
  return null;
}
