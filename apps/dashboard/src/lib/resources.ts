import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { useApi } from "@/app/api";

export function useResource<T>(path: string) {
  const api = useApi();
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      setData(await api<T>(path));
      setError(null);
    } catch (cause) {
      const message =
        cause instanceof Error ? cause.message : "Could not load data";
      setError(message);
      toast.error(message);
    } finally {
      setLoading(false);
    }
  }, [api, path]);

  useEffect(() => {
    void reload();
  }, [reload]);

  return { data, loading, error, reload };
}
