export type FolderLease = {
  acquire: (patrimonioId: number, token: string, leaseSeconds: number) => Promise<boolean>;
  release: (patrimonioId: number, token: string) => Promise<void>;
};

export async function withDriveFolderLease<T>(
  patrimonioId: number,
  lease: FolderLease,
  operation: () => Promise<T>,
  options: { attempts?: number; delayMs?: number; leaseSeconds?: number } = {},
): Promise<T> {
  if (!Number.isSafeInteger(patrimonioId) || patrimonioId <= 0) {
    throw new Error("invalid_patrimonio_id");
  }
  const attempts = options.attempts ?? 20;
  const delayMs = options.delayMs ?? 250;
  const leaseSeconds = options.leaseSeconds ?? 120;
  const token = crypto.randomUUID();
  let acquired = false;

  for (let attempt = 0; attempt < attempts; attempt++) {
    if (await lease.acquire(patrimonioId, token, leaseSeconds)) {
      acquired = true;
      break;
    }
    if (attempt + 1 < attempts) {
      await new Promise((resolve) => setTimeout(resolve, delayMs));
    }
  }
  if (!acquired) throw new Error("drive_folder_lease_busy");

  try {
    return await operation();
  } finally {
    await lease.release(patrimonioId, token);
  }
}

export async function ensureExactPatrimonioFolder(
  lookup: (label: "patrimonio" | "patrimonio_after_create") => Promise<string>,
  create: () => Promise<string>,
): Promise<string> {
  try {
    return await lookup("patrimonio");
  } catch (error) {
    if (!String(error).includes("drive_folder_missing:patrimonio")) throw error;
  }

  const createdId = await create();
  if (!createdId.trim()) throw new Error("drive_folder_create_missing_id");

  // Re-query by exact parent/name after creation. Zero or multiple matches fail closed.
  return await lookup("patrimonio_after_create");
}

export function selectUniqueDriveMatch<T>(files: T[]): T | null {
  if (files.length > 1) throw new Error("drive_duplicate_outbox_match");
  return files[0] ?? null;
}
