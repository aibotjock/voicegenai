import { useState } from "react";
import { AudioLines, CheckCircle2 } from "lucide-react";
import { PRODUCT_NAME } from "../../lib/brand";
import { useApp } from "../../lib/state/AppContext";
import { CreateVoiceFlow } from "../profiles/CreateVoiceFlow";
import { Button } from "../ui/Button";
import "./onboarding.css";

type Step = "welcome" | "create" | "ready";

/**
 * First-run: welcome → create voice → ready → Studio.
 * Deliberately short; no product tour.
 */
export function OnboardingFlow({ onDone }: { onDone: () => void }) {
  const { setActiveVoiceId } = useApp();
  const [step, setStep] = useState<Step>("welcome");
  const [voice, setVoice] = useState<{ id: string; name: string } | null>(null);

  return (
    <div className="onboarding">
      <div className="onboarding-card">
        {step === "welcome" && (
          <>
            <span className="onboarding-mark" aria-hidden="true">
              <AudioLines size={26} />
            </span>
            <h1 className="onboarding-title">Welcome to {PRODUCT_NAME}</h1>
            <p className="onboarding-body">
              Create a professional clone of your own voice and turn any script into
              finished audio. Everything runs on this device.
            </p>
            <Button variant="primary" size="lg" onClick={() => setStep("create")}>
              Create Your Voice
            </Button>
            <p className="onboarding-note">Takes about a minute.</p>
          </>
        )}

        {step === "create" && (
          <>
            <h1 className="onboarding-title">Create Your Voice</h1>
            <p className="onboarding-body">
              Record yourself reading anything — a paragraph from an article works well.
            </p>
            <CreateVoiceFlow
              onComplete={(id, name) => {
                setVoice({ id, name });
                setActiveVoiceId(id);
                setStep("ready");
              }}
            />
          </>
        )}

        {step === "ready" && (
          <>
            <span className="onboarding-mark onboarding-mark-success" aria-hidden="true">
              <CheckCircle2 size={26} />
            </span>
            <h1 className="onboarding-title">You're ready</h1>
            <p className="onboarding-body">
              {voice ? `“${voice.name}” is ready.` : "Your voice is ready."} Write a script,
              pick a style, and generate.
            </p>
            <Button variant="primary" size="lg" onClick={onDone}>
              Open Studio
            </Button>
          </>
        )}
      </div>
    </div>
  );
}
