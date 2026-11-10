export type FolderLease = {
  acquire: (patrimonioId: number, token: string, leaseSeconds: number) => Promise<boolean>;
  renew: (patrimonioId: number, token: string, leaseSeconds: number) => Promise<boolean>;
  release: (patrimonioId: number, token: string) => Promise<void>;
};

export async function withDriveFolderLease<T>(
  patrimonioId: number,
  lease: FolderLease,
  operation: (assertHeld: () => void) => Promise<T>,
  options: { attempts?: number; delayMs?: number; leaseSeconds?: number; heartbeatMs?: number } = {},
): Promise<T> {
  if (!Number.isSafeInteger(patrimonioId) || patrimonioId <= 0) throw new Error("invalid_patrimonio_id");
  const attempts = options.attempts ?? 20;
  const delayMs = options.delayMs ?? 250;
  const leaseSeconds = options.leaseSeconds ?? 120;
  const heartbeatMs = options.heartbeatMs ?? 30_000;
  if (!Number.isSafeInteger(leaseSeconds) || leaseSeconds < 30 || leaseSeconds > 300) {
    throw new Error("invalid_drive_folder_lease_seconds");
  }
  if (!Number.isSafeInteger(heartbeatMs) || heartbeatMs < 1 || heartbeatMs >= leaseSeconds * 500) {
    throw new Error("invalid_drive_folder_heartbeat_interval");
  }
  const token = crypto.randomUUID();
  let acquired = false;
  for (let attempt = 0; attempt < attempts; attempt++) {
    if (await lease.acquire(patrimonioId, token, leaseSeconds)) {
      acquired = true;
      break;
    }
    if (attempt + 1 < attempts) await new Promise((resolve) => setTimeout(resolve, delayMs));
  }
  if (!acquired) throw new Error("drive_folder_lease_busy");

  let active = true;
  let renewalInFlight: Promise<void> | null = null;
  let leaseLost: Error | null = null;
  const assertHeld = () => {
    if (leaseLost) throw leaseLost;
  };
  const timer = setInterval(() => {
    if (!active || renewalInFlight) return;
    renewalInFlight = (async () => {
      try {
        if (!await lease.renew(patrimonioId, token, leaseSeconds)) {
          leaseLost = new Error("drive_folder_lease_lost");
        }
      } catch {
        leaseLost = new Error("drive_folder_lease_renew_failed");
      }
    })().finally(() => { renewalInFlight = null; });
  }, heartbeatMs);

  try {
    const result = await operation(assertHeld);
    // Do not return a successful result while a heartbeat renewal is still unresolved.
    // The in-flight renewal may be the first signal that this worker lost the lease.
    if (renewalInFlight) await renewalInFlight;
    assertHeld();
    return result;
  } finally {
    active = false;
    clearInterval(timer);
    if (renewalInFlight) await renewalInFlight;
    try {
      await lease.release(patrimonioId, token);
    } catch (error) {
      if (!leaseLost) throw error;
    }
  }
}

export async function ensureExactPatrimonioFolder(
  lookup: (label: "patrimonio" | "patrimonio_after_create") => Promise<string>,
  create: () => Promise<string>,
  assertHeld: () => void = () => {},
): Promise<string> {
  assertHeld();
  try {
    return await lookup("patrimonio");
  } catch (error) {
    if (!String(error).includes("drive_folder_missing:patrimonio")) throw error;
  }
  assertHeld();
  const createdId = await create();
  if (!createdId.trim()) throw new Error("drive_folder_create_missing_id");
  assertHeld();
  return await lookup("patrimonio_after_create");
}

export function selectUniqueDriveMatch<T>(files: T[]): T | null {
  if (files.length > 1) throw new Error("drive_duplicate_outbox_match");
  return files[0] ?? null;
}

export function assertOutboxPatrimonioMatches(outboxPatrimonioId: number, fotoPatrimonioId: number): void {
  if (!Number.isSafeInteger(outboxPatrimonioId) || !Number.isSafeInteger(fotoPatrimonioId) ||
      outboxPatrimonioId <= 0 || fotoPatrimonioId <= 0 || outboxPatrimonioId !== fotoPatrimonioId) {
    throw new Error("outbox_patrimonio_mismatch");
  }
}
