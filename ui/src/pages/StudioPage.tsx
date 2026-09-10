import { useEffect, useMemo, useRef, useState } from "react";
import { friendlyError } from "../lib/api/errors";
import {
  useExportJob,
  useGenerate,
  useGenerationJob,
  usePresets,
  useProfiles,
} from "../lib/api/hooks";
import type { ExportResult, GlossaryItem } from "../lib/api/types";
import { useApp } from "../lib/state/AppContext";
import { CreateVoiceFlow } from "../components/profiles/CreateVoiceFlow";
import { VoiceSelector } from "../components/profiles/VoiceSelector";
import { ScriptEditor } from "../components/studio/ScriptEditor";
import { PronunciationEditor } from "../components/studio/PronunciationEditor";
import { PresetGrid } from "../components/studio/PresetGrid";
import {
  AdvancedPanel,
  DEFAULT_ADVANCED,
  type AdvancedOptions,
} from "../components/studio/AdvancedPanel";
import {
  GenerateControls,
  generationReadiness,
} from "../components/studio/GenerateControls";
import { GenerationProgress } from "../components/studio/GenerationProgress";
import { SegmentReview } from "../components/studio/SegmentReview";
import { OutputPanel } from "../components/studio/OutputPanel";
import { Dialog } from "../components/ui/Dialog";
import { EmptyState } from "../components/ui/Feedback";
import { AudioLines } from "lucide-react";

/**
 * Studio: voice → script → style → generate → review → export.
 * Layout: main column (voice + script), right rail (style + generate),
 * bottom output region (progress / review / player).
 */
export function StudioPage() {
  const {
    activeVoiceId,
    setActiveVoiceId,
    sidecar,
    toast,
    addSessionGeneration,
    updateSessionGeneration,
  } = useApp();
  const { data: profiles } = useProfiles();
  const { data: presets } = usePresets();
  const generate = useGenerate();
  const exportJob = useExportJob();

  const [script, setScript] = useState("");
  const [glossary, setGlossary] = useState<GlossaryItem[]>([]);
  const [design, setDesign] = useState<string | null>(null);
  const [advanced, setAdvanced] = useState<AdvancedOptions>(DEFAULT_ADVANCED);
  const [jobId, setJobId] = useState<string | null>(null);
  const [preview, setPreview] = useState<ExportResult | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [lastExport, setLastExport] = useState<ExportResult | null>(null);
  const [createOpen, setCreateOpen] = useState(false);

  const job = useGenerationJob(jobId);
  const recordedJobRef = useRef<string | null>(null);
  const previewJobRef = useRef<string | null>(null);

  const voice = useMemo(
    () => profiles?.find((p) => p.id === activeVoiceId) ?? null,
    [profiles, activeVoiceId],
  );

  // Default the style from backend health/presets once known.
  useEffect(() => {
    if (!design && presets) {
      setDesign(presets["podcast"] ? "podcast" : Object.keys(presets)[0] ?? null);
    }
  }, [presets, design]);

  const generating =
    !!job && (job.status === "queued" || job.status === "running");

  const readiness = generationReadiness({
    sidecarReady: sidecar.status === "ready",
    voice,
    script,
    design,
    generating,
  });

  // When a job completes: record it in the session library and create the
  // WAV preview export (single format) so the player can load the result.
  useEffect(() => {
    if (!job || job.status !== "done" || recordedJobRef.current === job.id) return;
    recordedJobRef.current = job.id;
    const voiceName = voice?.name ?? "Voice";
    const designName =
      (job.result.design && presets?.[job.result.design]?.name) || job.result.design || "Style";
    addSessionGeneration({
      jobId: job.id,
      createdAt: job.created_at,
      voiceName,
      designName,
      scriptExcerpt: script.trim().slice(0, 140),
      segments: job.result.segments ?? job.segments.length,
      flagged: job.result.flagged ?? 0,
      elapsedS: job.result.elapsed_s ?? null,
    });
    if ((job.result.flagged ?? 0) > 0) {
      toast("info", `${job.result.flagged} section(s) need review — see Section review.`);
    }
    if (previewJobRef.current !== job.id) {
      previewJobRef.current = job.id;
      setPreviewLoading(true);
      exportJob
        .mutateAsync({ jobId: job.id, req: { formats: "wav", stem: `voicegen-${job.id}` } })
        .then((res) => {
          setPreview(res);
          setLastExport(res);
          updateSessionGeneration(job.id, {
            exportMasterPath: res.master,
            exportStem: `voicegen-${job.id}`,
          });
        })
        .catch((err) => {
          toast("error", friendlyError(err, "Could not prepare the audio preview. Use Export to save manually."));
        })
        .finally(() => setPreviewLoading(false));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job?.status]);

  const startGeneration = async () => {
    if (!voice || !design) return;
    setPreview(null);
    setLastExport(null);
    setJobId(null);
    try {
      const res = await generate.mutateAsync({
        script,
        profile_id: voice.id,
        design,
        glossary,
        engine: advanced.engine,
        seed: advanced.seed,
        lufs: advanced.lufs,
        check_wer: advanced.checkWer,
      });
      setJobId(res.job_id);
    } catch (err) {
      toast("error", friendlyError(err, "Could not start generation."));
    }
  };

  const onVoiceCreated = (id: string) => {
    setActiveVoiceId(id);
    setCreateOpen(false);
  };

  const createDialog = (
    <Dialog
      open={createOpen}
      onClose={() => setCreateOpen(false)}
      title="Create your voice"
      wide
    >
      <CreateVoiceFlow onComplete={onVoiceCreated} onCancel={() => setCreateOpen(false)} />
    </Dialog>
  );

  if (profiles && profiles.length === 0) {
    return (
      <>
        <EmptyState
          icon={<AudioLines size={22} />}
          title="Create a voice to start"
          body="Your studio needs a voice. It takes about a minute — record yourself or upload audio, and pass the recording check."
          action={
            <button type="button" className="btn btn-primary btn-lg" onClick={() => setCreateOpen(true)}>
              Create Voice
            </button>
          }
        />
        {createDialog}
      </>
    );
  }

  return (
    <div>
      <div className="studio-grid">
        <div className="studio-main">
          <VoiceSelector onCreateVoice={() => setCreateOpen(true)} />
          <div>
            <h2 className="section-title" style={{ marginBottom: 8 }}>
              Script
            </h2>
            <ScriptEditor value={script} onChange={setScript} disabled={generating} />
          </div>
          <PronunciationEditor value={glossary} onChange={setGlossary} />
        </div>

        <aside className="studio-rail" aria-label="Style and generation">
          <div>
            <h2 className="section-title" style={{ marginBottom: 8 }}>
              Style
            </h2>
            <PresetGrid selected={design} onSelect={setDesign} />
          </div>
          <AdvancedPanel
            value={advanced}
            onChange={setAdvanced}
            onReset={() => setAdvanced(DEFAULT_ADVANCED)}
          />
          <GenerateControls
            readiness={readiness}
            generating={generating}
            onGenerate={() => void startGeneration()}
          />
        </aside>
      </div>

      <div className="studio-output">
        {job && job.status !== "done" ? <GenerationProgress job={job} /> : null}
        {job ? <SegmentReview job={job} /> : null}
        {job && job.status === "done" ? (
          <OutputPanel
            job={job}
            preview={preview}
            previewLoading={previewLoading}
            lastExport={lastExport}
            onExported={(res) => {
              setLastExport(res);
              updateSessionGeneration(job.id, { exportMasterPath: res.master });
              toast("success", "Export complete — provenance embedded.");
            }}
          />
        ) : null}
      </div>

      {createDialog}
    </div>
  );
}
