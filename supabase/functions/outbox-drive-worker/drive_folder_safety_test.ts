import {
  assertOutboxPatrimonioMatches,
  ensureExactPatrimonioFolder,
  selectUniqueDriveMatch,
  withDriveFolderLease,
} from "./drive_folder_safety.ts";

function assert(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message);
}

async function expectRejects(run: () => Promise<unknown>, includes: string) {
  try {
    await run();
  } catch (error) {
    assert(String(error).includes(includes), `expected error containing ${includes}, got ${String(error)}`);
    return;
  }
  throw new Error(`expected rejection containing ${includes}`);
}

Deno.test("existing exact patrimonio folder is reused without creating", async () => {
  const labels: string[] = [];
  let creates = 0;
  const id = await ensureExactPatrimonioFolder(async (label) => {
    labels.push(label);
    return "folder-existing";
  }, async () => {
    creates++;
    return "unexpected";
  });
  assert(id === "folder-existing", "existing folder id must be returned");
  assert(creates === 0, "existing folder must not be recreated");
  assert(labels.join(",") === "patrimonio", "lookup should happen once");
});

Deno.test("missing folder is created then looked up again by exact identity", async () => {
  const labels: string[] = [];
  let creates = 0;
  const id = await ensureExactPatrimonioFolder(async (label) => {
    labels.push(label);
    if (label === "patrimonio") throw new Error("drive_folder_missing:patrimonio");
    return "folder-after-create";
  }, async () => {
    creates++;
    return "created-id";
  });
  assert(id === "folder-after-create", "post-create lookup id must be returned");
  assert(creates === 1, "one folder creation expected");
  assert(labels.join(",") === "patrimonio,patrimonio_after_create", "post-create lookup required");
});

Deno.test("ambiguous folder lookup fails closed without creating", async () => {
  let creates = 0;
  await expectRejects(
    () => ensureExactPatrimonioFolder(async () => {
      throw new Error("drive_folder_ambiguous:patrimonio");
    }, async () => {
      creates++;
      return "should-not-create";
    }),
    "drive_folder_ambiguous",
  );
  assert(creates === 0, "ambiguous destination must never trigger creation");
});

Deno.test("Drive create HTTP failure fails closed without a post-create lookup", async () => {
  const labels: string[] = [];
  await expectRejects(
    () => ensureExactPatrimonioFolder(async (label) => {
      labels.push(label);
      if (label === "patrimonio") throw new Error("drive_folder_missing:patrimonio");
      return "unexpected";
    }, async () => {
      throw new Error("drive_folder_create_failed:patrimonio:403");
    }),
    "drive_folder_create_failed:patrimonio:403",
  );
  assert(labels.join(",") === "patrimonio", "failed create must not trigger post-create lookup");
});

Deno.test("missing create response id fails closed", async () => {
  await expectRejects(
    () => ensureExactPatrimonioFolder(async () => {
      throw new Error("drive_folder_missing:patrimonio");
    }, async () => ""),
    "drive_folder_create_missing_id",
  );
});

Deno.test("database lease serializes two concurrent operations for one patrimonio", async () => {
  let held = false;
  let active = 0;
  let maxActive = 0;
  const lease = {
    acquire: async (_id: number, _token: string, _seconds: number) => {
      if (held) return false;
      held = true;
      return true;
    },
    renew: async (_id: number, _token: string, _seconds: number) => held,
    release: async (_id: number, _token: string) => {
      held = false;
    },
  };
  const operation = async () => {
    active++;
    maxActive = Math.max(maxActive, active);
    await new Promise((resolve) => setTimeout(resolve, 8));
    active--;
  };
  await Promise.all([
    withDriveFolderLease(22, lease, operation, { attempts: 40, delayMs: 1, heartbeatMs: 2 }),
    withDriveFolderLease(22, lease, operation, { attempts: 40, delayMs: 1 }),
  ]);
  assert(maxActive === 1, `operations overlapped; max active was ${maxActive}`);
  assert(!held, "lease should be released after both operations");
});

Deno.test("lease is released when the protected operation throws", async () => {
  let held = false;
  const lease = {
    acquire: async () => {
      if (held) return false;
      held = true;
      return true;
    },
    renew: async () => held,
    release: async () => {
      held = false;
    },
  };
  await expectRejects(
    () => withDriveFolderLease(23, lease, async () => {
      throw new Error("simulated_operation_failure");
    }, { attempts: 1, delayMs: 0 }),
    "simulated_operation_failure",
  );
  assert(!held, "lease must be released after an operation failure");
});

Deno.test("outbox event and photo must reference the same patrimonio", () => {
  assertOutboxPatrimonioMatches(22, 22);
  let rejected = false;
  try {
    assertOutboxPatrimonioMatches(22, 23);
  } catch (error) {
    rejected = String(error).includes("outbox_patrimonio_mismatch");
  }
  assert(rejected, "mismatched patrimonio IDs must fail closed");
});

Deno.test("duplicate Drive matches fail closed instead of choosing the first", () => {
  assert(selectUniqueDriveMatch([{ id: "one" }])?.id === "one", "single match should be reused");
  assert(selectUniqueDriveMatch([]) === null, "no match should permit upload attempt");
  let rejected = false;
  try {
    selectUniqueDriveMatch([{ id: "one" }, { id: "two" }]);
  } catch (error) {
    rejected = String(error).includes("drive_duplicate_outbox_match");
  }
  assert(rejected, "multiple matches must fail closed");
});


Deno.test("lease heartbeat renews a long-running folder operation", async () => {
  let held = false;
  let renewals = 0;
  const lease = {
    acquire: async () => { if (held) return false; held = true; return true; },
    renew: async () => { renewals++; return held; },
    release: async () => { held = false; },
  };
  await withDriveFolderLease(24, lease, async (assertHeld) => {
    await new Promise((resolve) => setTimeout(resolve, 15));
    assertHeld();
  }, { attempts: 1, heartbeatMs: 2 });
  assert(renewals > 0, "long operation should trigger lease renewal");
  assert(!held, "lease should be released after renewal");
});

Deno.test("lost lease prevents the next protected folder operation", async () => {
  let held = false;
  const lease = {
    acquire: async () => { held = true; return true; },
    renew: async () => false,
    release: async () => { held = false; },
  };
  await expectRejects(
    () => withDriveFolderLease(25, lease, async (assertHeld) => {
      await new Promise((resolve) => setTimeout(resolve, 10));
      assertHeld();
      throw new Error("must_not_reach");
    }, { attempts: 1, heartbeatMs: 1 }),
    "drive_folder_lease_lost",
  );
  assert(!held, "lease should be released after loss is detected");
});

Deno.test("lease loss during folder creation blocks post-create lookup and finalization path", async () => {
  let leaseHeld = true;
  let creates = 0;
  let postCreateLookups = 0;
  await expectRejects(
    () => ensureExactPatrimonioFolder(async (label) => {
      if (label === "patrimonio") throw new Error("drive_folder_missing:patrimonio");
      if (label === "patrimonio_after_create") postCreateLookups++;
      return "folder-id";
    }, async () => {
      creates++;
      leaseHeld = false;
      return "created-folder-id";
    }, () => {
      if (!leaseHeld) throw new Error("drive_folder_lease_lost");
    }),
    "drive_folder_lease_lost",
  );
  assert(creates === 1, "folder creation should be attempted once");
  assert(postCreateLookups === 0, "lost lease must block post-create lookup");
});
