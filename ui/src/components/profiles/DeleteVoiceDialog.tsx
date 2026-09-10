import { useState } from "react";
import { friendlyError } from "../../lib/api/errors";
import { useDeleteProfile } from "../../lib/api/hooks";
import type { VoiceProfile } from "../../lib/api/types";
import { useApp } from "../../lib/state/AppContext";
import { Button } from "../ui/Button";
import { Dialog } from "../ui/Dialog";
import { Spinner } from "../ui/Feedback";

interface DeleteVoiceDialogProps {
  profile: VoiceProfile;
  open: boolean;
  onClose: () => void;
  onDeleted: () => void;
}

/**
 * "Delete my voice" — security-sensitive, explicit confirmation.
 * Success is only reported after the backend confirms a verified wipe
 * (zero residual files).
 */
export function DeleteVoiceDialog({ profile, open, onClose, onDeleted }: DeleteVoiceDialogProps) {
  const del = useDeleteProfile();
  const { toast, activeVoiceId, setActiveVoiceId } = useApp();
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const confirm = async () => {
    setWorking(true);
    setError(null);
    try {
      const res = await del.mutateAsync(profile.id);
      if (res.ok && res.residual === 0) {
        if (activeVoiceId === profile.id) setActiveVoiceId(null);
        toast("success", `“${profile.name}” was permanently deleted from this device.`);
        onDeleted();
        onClose();
      } else {
        setError(
          "Deletion was not fully completed — some files could not be removed. Nothing about this voice is considered deleted.",
        );
      }
    } catch (err) {
      setError(friendlyError(err, "Deletion was not fully completed."));
    } finally {
      setWorking(false);
    }
  };

  return (
    <Dialog
      open={open}
      onClose={() => !working && onClose()}
      title={`Delete “${profile.name}”?`}
      actions={
        <>
          <Button variant="ghost" onClick={onClose} disabled={working}>
            Cancel
          </Button>
          <Button variant="danger" onClick={() => void confirm()} disabled={working}>
            {working ? <Spinner /> : null}
            Delete Voice
          </Button>
        </>
      }
    >
      <p>
        This permanently removes the stored voice data from this device, including
        the recording and voiceprint. This cannot be undone.
      </p>
      {error ? (
        <p role="alert" style={{ color: "var(--danger)", marginTop: 12 }}>
          {error}
        </p>
      ) : null}
    </Dialog>
  );
}
