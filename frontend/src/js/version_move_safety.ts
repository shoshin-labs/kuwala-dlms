type Folder = { id: number; parent: number | null; breadcrumb?: { id: number }[] };

/** Refuse missing, self, descendant, or malformed destination paths. */
export function folderDestinationAllowed(sourceId: number, destination: Folder, folders: Folder[]) {
    if (!Number.isSafeInteger(sourceId) || sourceId < 1 || !destination ||
        !Number.isSafeInteger(destination.id) || destination.id < 1 ||
        destination.breadcrumb?.some((folder) => folder.id === sourceId)) return false;
    const seen = new Set<number>();
    let current: Folder | undefined = destination;
    while (current) {
        if (current.id === sourceId || seen.has(current.id)) return false;
        seen.add(current.id);
        if (current.parent === null) return true;
        current = folders.find((folder) => folder.id === current!.parent);
    }
    return false;
}

/** A failed destination write must never remove the existing membership. */
export async function transferMembership(addDestination: () => Promise<unknown>, removeSource: () => Promise<unknown>) {
    await addDestination();
    await removeSource();
}
