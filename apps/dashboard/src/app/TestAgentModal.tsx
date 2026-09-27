import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  ChevronDown,
  ChevronUp,
  MessageSquare,
  Mic,
  MicOff,
  Phone,
  PhoneOff,
  Radio,
  User,
  Volume2,
} from "lucide-react";
import { toast } from "sonner";
import { useApi } from "./api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { PhoneInput } from "@/components/ui/phone-input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

type Agent = {
  id: string;
  name: string;
  active_version_id?: string | null;
  published_version_id?: string | null;
  latest_version_id?: string | null;
  latest_version_status?: string | null;
};

type Contact = {
  id: string;
  name: string;
  phone_number: string;
  timezone?: string | null;
  business?: string | null;
  source?: string | null;
  language?: string | null;
  metadata?: Record<string, unknown> | null;
  created_at?: string | null;
};

type IntegrationConnection = {
  id: string;
  label: string;
  provider: string;
  enabled: boolean;
  deleted_at?: string | null;
  secret_names?: string[];
};

type BrowserSessionResponse = {
  id: string;
  run_id: string;
  status: string;
  contact_id?: string | null;
  created_at?: string;
  expires_at?: string;
};

export function TestAgentModal() {
  const api = useApi();
  const [open, setOpen] = useState(false);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [selectedAgentId, setSelectedAgentId] = useState("");
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [connections, setConnections] = useState<IntegrationConnection[]>([]);

  // Context Mode: contact | custom | none
  const [contextMode, setContextMode] = useState<"contact" | "custom" | "none">("contact");
  const [selectedContactId, setSelectedContactId] = useState("");
  const [usePhoneOverride, setUsePhoneOverride] = useState(false);
  const [overridePhone, setOverridePhone] = useState("");

  // Custom Lead fields
  const [customPhone, setCustomPhone] = useState("");
  const [customName, setCustomName] = useState("Test Caller");
  const [customBusiness, setCustomBusiness] = useState("");
  const [customQuery, setCustomQuery] = useState("");
  const [customSource, setCustomSource] = useState("browser_test");
  const [showAdvancedCustom, setShowAdvancedCustom] = useState(false);

  // Active call identity for live banner & post-call linkage
  const [activeContactId, setActiveContactId] = useState<string | null>(null);
  const [activeDisplayName, setActiveDisplayName] = useState<string>("Anonymous");
  const [activeTargetPhone, setActiveTargetPhone] = useState<string | null>(null);

  const [callState, setCallState] = useState<
    "idle" | "requesting" | "connecting" | "connected" | "ended"
  >("idle");
  const [isMuted, setIsMuted] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [duration, setDuration] = useState(0);
  const [runId, setRunId] = useState<string | null>(null);

  const pcRef = useRef<RTCPeerConnection | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const sessionIdRef = useRef<string | null>(null);
  const pcIdRef = useRef<string | null>(null);
  const timerRef = useRef<number | null>(null);
  const animFrameRef = useRef<number | null>(null);

  useEffect(() => {
    if (!open) return;
    Promise.all([
      api<{ agents: Agent[] }>("/agents"),
      api<{ contacts: Contact[] }>("/contacts"),
      api<{ connections: IntegrationConnection[] }>("/integrations"),
    ])
      .then(([agentsData, contactsData, integrationsData]) => {
        setAgents(agentsData.agents);
        setContacts(contactsData.contacts);
        setConnections(integrationsData.connections || []);

        const preferredAgent = agentsData.agents.find(
          (a) => a.active_version_id || a.published_version_id || a.latest_version_id
        );
        if (preferredAgent) {
          setSelectedAgentId(preferredAgent.id);
        } else if (agentsData.agents.length > 0) {
          setSelectedAgentId(agentsData.agents[0].id);
        }

        if (contactsData.contacts.length > 0 && !selectedContactId) {
          setSelectedContactId(contactsData.contacts[0].id);
        }
      })
      .catch((err) => {
        toast.error("Failed to load options: " + (err.message || String(err)));
      });
  }, [api, open]);

  const hasWhatsApp = connections.some(
    (c) => c.provider === "whatsapp_cloud" && c.enabled && !c.deleted_at
  );

  const selectedContact = contacts.find((c) => c.id === selectedContactId);

  // Duration timer
  useEffect(() => {
    if (callState === "connected") {
      setDuration(0);
      timerRef.current = window.setInterval(() => {
        setDuration((prev) => prev + 1);
      }, 1000);
    } else {
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    }
    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [callState]);

  const cleanupCall = () => {
    if (animFrameRef.current) {
      cancelAnimationFrame(animFrameRef.current);
      animFrameRef.current = null;
    }
    if (audioContextRef.current) {
      audioContextRef.current.close().catch(() => {});
      audioContextRef.current = null;
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    if (pcRef.current) {
      pcRef.current.close();
      pcRef.current = null;
    }
    sessionIdRef.current = null;
    pcIdRef.current = null;
    setIsMuted(false);
    setIsSpeaking(false);
  };

  const startTestCall = async () => {
    try {
      setCallState("requesting");
      const agent = agents.find((a) => a.id === selectedAgentId);
      const agentVersionId =
        agent?.active_version_id ||
        agent?.published_version_id ||
        agent?.latest_version_id ||
        undefined;

      const payload: {
        agent_id?: string;
        agent_version_id?: string;
        contact_id?: string;
        phone_number?: string;
        contact_variables?: Record<string, string>;
      } = {
        agent_id: selectedAgentId || undefined,
        agent_version_id: agentVersionId,
      };

      let displayName = "Anonymous";
      let targetPhone: string | null = null;
      let linkedContactId: string | null = null;

      if (contextMode === "contact") {
        if (selectedContact) {
          payload.contact_id = selectedContact.id;
          linkedContactId = selectedContact.id;
          displayName = selectedContact.name;
          if (usePhoneOverride && overridePhone.trim()) {
            payload.phone_number = overridePhone.trim();
            targetPhone = overridePhone.trim();
          } else {
            targetPhone = selectedContact.phone_number;
          }
        }
      } else if (contextMode === "custom") {
        displayName = customName.trim() || "Test Caller";
        if (customPhone.trim()) {
          payload.phone_number = customPhone.trim();
          targetPhone = customPhone.trim();
        }
        const vars: Record<string, string> = {
          name: displayName,
        };
        if (customBusiness.trim()) vars.business = customBusiness.trim();
        if (customQuery.trim()) vars.query = customQuery.trim();
        if (customSource.trim()) vars.source = customSource.trim();
        payload.contact_variables = vars;
      }

      setActiveContactId(linkedContactId);
      setActiveDisplayName(displayName);
      setActiveTargetPhone(targetPhone);

      // 1. Create browser session
      const session = await api<BrowserSessionResponse>("/browser-sessions", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      sessionIdRef.current = session.id;
      setRunId(session.run_id);
      setCallState("connecting");

      // 2. Access microphone
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
      streamRef.current = stream;

      // 3. Create WebRTC PeerConnection
      const pc = new RTCPeerConnection({
        iceServers: [{ urls: "stun:stun.l.google.com:19302" }],
      });
      pcRef.current = pc;

      // Add local audio tracks
      stream.getAudioTracks().forEach((track) => {
        pc.addTrack(track, stream);
      });

      // Handle remote incoming audio track
      pc.ontrack = (event) => {
        if (audioRef.current && event.streams[0]) {
          audioRef.current.srcObject = event.streams[0];
          audioRef.current.play().catch(console.error);

          // Audio level detection to identify if agent is speaking
          try {
            const AudioCtx =
              window.AudioContext ||
              (window as unknown as { webkitAudioContext: typeof AudioContext })
                .webkitAudioContext;
            const ctx = new AudioCtx();
            audioContextRef.current = ctx;
            const source = ctx.createMediaStreamSource(event.streams[0]);
            const analyser = ctx.createAnalyser();
            analyser.fftSize = 256;
            source.connect(analyser);

            const dataArray = new Uint8Array(analyser.frequencyBinCount);
            const checkVolume = () => {
              analyser.getByteFrequencyData(dataArray);
              let sum = 0;
              for (let i = 0; i < dataArray.length; i++) {
                sum += dataArray[i];
              }
              const avg = sum / dataArray.length;
              setIsSpeaking(avg > 15);
              animFrameRef.current = requestAnimationFrame(checkVolume);
            };
            checkVolume();
          } catch {
            // Audio context visualizer fallback
          }
        }
      };

      // Trickle ICE candidate handler
      pc.onicecandidate = (event) => {
        if (event.candidate && pcIdRef.current && sessionIdRef.current) {
          api(`/browser-sessions/${sessionIdRef.current}/offer`, {
            method: "PATCH",
            body: JSON.stringify({
              pc_id: pcIdRef.current,
              candidates: [
                {
                  candidate: event.candidate.candidate,
                  sdpMid: event.candidate.sdpMid || "0",
                  sdpMLineIndex: event.candidate.sdpMLineIndex ?? 0,
                },
              ],
            }),
          }).catch(() => {});
        }
      };

      pc.onconnectionstatechange = () => {
        if (pc.connectionState === "connected") {
          setCallState("connected");
        } else if (
          pc.connectionState === "disconnected" ||
          pc.connectionState === "failed" ||
          pc.connectionState === "closed"
        ) {
          if (callState === "connected") {
            setCallState("ended");
            cleanupCall();
          }
        }
      };

      // 4. Create and send offer
      const offer = await pc.createOffer({ offerToReceiveAudio: true });
      await pc.setLocalDescription(offer);

      const answer = await api<{ sdp: string; type: string; pc_id: string }>(
        `/browser-sessions/${session.id}/offer`,
        {
          method: "POST",
          body: JSON.stringify({
            sdp: offer.sdp,
            type: offer.type,
          }),
        }
      );

      pcIdRef.current = answer.pc_id;
      await pc.setRemoteDescription(
        new RTCSessionDescription({
          sdp: answer.sdp,
          type: answer.type as RTCSdpType,
        })
      );
      setCallState("connected");
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      toast.error("Failed to start test call: " + msg);
      setCallState("idle");
      cleanupCall();
    }
  };

  const endTestCall = async () => {
    if (sessionIdRef.current) {
      try {
        await api(`/browser-sessions/${sessionIdRef.current}`, {
          method: "DELETE",
        });
      } catch {
        // Ignored
      }
    }
    cleanupCall();
    setCallState("ended");
  };

  const toggleMute = () => {
    if (streamRef.current) {
      const audioTracks = streamRef.current.getAudioTracks();
      const nextMuted = !isMuted;
      audioTracks.forEach((track) => {
        track.enabled = !nextMuted;
      });
      setIsMuted(nextMuted);
    }
  };

  const formatTimer = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
  };

  const handleOpenChange = (nextOpen: boolean) => {
    if (!nextOpen && (callState === "connected" || callState === "connecting")) {
      endTestCall();
    }
    if (!nextOpen) {
      cleanupCall();
      setCallState("idle");
    }
    setOpen(nextOpen);
  };

  return (
    <>
      <audio ref={audioRef} autoPlay playsInline className="hidden" />
      <Dialog open={open} onOpenChange={handleOpenChange}>
        <DialogTrigger asChild>
          <Button variant="outline" size="sm" className="gap-2">
            <Radio className="size-4 text-emerald-500 animate-pulse" />
            <span>Test Agent</span>
          </Button>
        </DialogTrigger>
        <DialogContent className="sm:max-w-lg max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Test Agent</DialogTitle>
            <DialogDescription>
              Speak directly with your configured agent using your browser microphone and speakers.
            </DialogDescription>
          </DialogHeader>

          {callState === "idle" && (
            <div className="flex flex-col gap-4 py-2">
              {/* Agent Selection */}
              <label className="flex flex-col gap-1.5">
                <span className="text-xs font-medium text-muted-foreground">Select Agent</span>
                <NativeSelect
                  value={selectedAgentId}
                  onChange={(e) => setSelectedAgentId(e.target.value)}
                >
                  {agents.map((agent) => {
                    const status = agent.active_version_id
                      ? "Active"
                      : agent.latest_version_status === "published"
                        ? "Published"
                        : "Draft";
                    return (
                      <NativeSelectOption key={agent.id} value={agent.id}>
                        {agent.name} ({status})
                      </NativeSelectOption>
                    );
                  })}
                </NativeSelect>
              </label>

              {/* Caller Identity & Context Tabs */}
              <div className="flex flex-col gap-2 rounded-lg border bg-muted/20 p-3">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium text-muted-foreground">
                    Caller Identity & Delivery Context
                  </span>
                  {hasWhatsApp ? (
                    <Badge
                      variant="outline"
                      className="text-[11px] gap-1 text-emerald-600 border-emerald-300 dark:border-emerald-800 dark:text-emerald-400"
                    >
                      <MessageSquare className="size-3" /> WhatsApp Live
                    </Badge>
                  ) : (
                    <Badge variant="outline" className="text-[11px] gap-1 text-muted-foreground">
                      <MessageSquare className="size-3" /> WhatsApp Offline
                    </Badge>
                  )}
                </div>

                <Tabs
                  value={contextMode}
                  onValueChange={(val) =>
                    setContextMode(val as "contact" | "custom" | "none")
                  }
                  className="w-full"
                >
                  <TabsList className="grid w-full grid-cols-3">
                    <TabsTrigger value="contact">Contact</TabsTrigger>
                    <TabsTrigger value="custom">Custom Lead</TabsTrigger>
                    <TabsTrigger value="none">No Context</TabsTrigger>
                  </TabsList>

                  {/* Mode 1: Contact Picker */}
                  <TabsContent value="contact" className="space-y-3 pt-2">
                    {contacts.length === 0 ? (
                      <div className="rounded border border-dashed p-3 text-center text-xs text-muted-foreground">
                        No contacts found. Use Custom Lead or create a contact in the Contacts tab.
                      </div>
                    ) : (
                      <>
                        <label className="flex flex-col gap-1.5">
                          <span className="text-xs font-medium text-muted-foreground">
                            Choose Contact Persona
                          </span>
                          <NativeSelect
                            value={selectedContactId}
                            onChange={(e) => setSelectedContactId(e.target.value)}
                          >
                            {contacts.map((c) => (
                              <NativeSelectOption key={c.id} value={c.id}>
                                {c.name} ({c.phone_number})
                              </NativeSelectOption>
                            ))}
                          </NativeSelect>
                        </label>

                        {selectedContact && (
                          <div className="rounded-md border bg-background/50 p-2.5 text-xs space-y-1">
                            <div className="flex items-center justify-between font-medium">
                              <span className="flex items-center gap-1.5">
                                <User className="size-3.5 text-muted-foreground" />
                                {selectedContact.name}
                              </span>
                              <span className="text-muted-foreground">
                                {selectedContact.timezone || "UTC"}
                              </span>
                            </div>
                            <div className="text-muted-foreground flex items-center gap-1.5">
                              <Phone className="size-3" />
                              <span>{selectedContact.phone_number}</span>
                              {selectedContact.business && (
                                <span>· {selectedContact.business}</span>
                              )}
                              {selectedContact.source && (
                                <span>· Source: {selectedContact.source}</span>
                              )}
                            </div>
                            {selectedContact.metadata &&
                              Object.keys(selectedContact.metadata).length > 0 && (
                                <div className="text-[11px] text-muted-foreground pt-1 border-t border-dashed mt-1.5">
                                  {Object.entries(selectedContact.metadata)
                                    .slice(0, 2)
                                    .map(([k, v]) => (
                                      <span key={k} className="mr-3">
                                        <span className="font-medium text-foreground">{k}:</span>{" "}
                                        {String(v)}
                                      </span>
                                    ))}
                                </div>
                              )}
                          </div>
                        )}

                        <div className="pt-1">
                          <label className="flex items-center gap-2 cursor-pointer text-xs text-muted-foreground">
                            <input
                              type="checkbox"
                              checked={usePhoneOverride}
                              onChange={(e) => setUsePhoneOverride(e.target.checked)}
                              className="rounded border-input"
                            />
                            <span>Deliver WhatsApp messages to a different test number</span>
                          </label>

                          {usePhoneOverride && (
                            <div className="mt-2 space-y-1">
                              <PhoneInput
                                value={overridePhone}
                                onChange={setOverridePhone}
                                placeholder="Enter test phone number"
                              />
                              <p className="text-[11px] text-muted-foreground">
                                The agent will address you as {selectedContact?.name || "the contact"},
                                but WhatsApp tools will deliver to this number.
                              </p>
                            </div>
                          )}
                        </div>
                      </>
                    )}
                  </TabsContent>

                  {/* Mode 2: Custom Lead */}
                  <TabsContent value="custom" className="space-y-3 pt-2">
                    <div className="space-y-1.5">
                      <span className="text-xs font-medium text-muted-foreground">
                        Test Phone Number (for WhatsApp delivery)
                      </span>
                      <PhoneInput
                        value={customPhone}
                        onChange={setCustomPhone}
                        placeholder="e.g. 7304058886"
                      />
                      <p className="text-[11px] text-muted-foreground">
                        Agent tools will send WhatsApp messages to this phone number.
                      </p>
                    </div>

                    <div className="space-y-1.5">
                      <span className="text-xs font-medium text-muted-foreground">
                        Caller Name (Interpolated into prompts)
                      </span>
                      <Input
                        value={customName}
                        onChange={(e) => setCustomName(e.target.value)}
                        placeholder="e.g. Alex Mercer"
                      />
                    </div>

                    <div>
                      <button
                        type="button"
                        onClick={() => setShowAdvancedCustom(!showAdvancedCustom)}
                        className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
                      >
                        <span>Advanced Context Variables</span>
                        {showAdvancedCustom ? (
                          <ChevronUp className="size-3" />
                        ) : (
                          <ChevronDown className="size-3" />
                        )}
                      </button>

                      {showAdvancedCustom && (
                        <div className="mt-2 space-y-2 rounded-md border bg-background/50 p-2.5">
                          <label className="flex flex-col gap-1">
                            <span className="text-[11px] text-muted-foreground">
                              Query (e.g. {"{{ query }}"})
                            </span>
                            <Input
                              value={customQuery}
                              onChange={(e) => setCustomQuery(e.target.value)}
                              placeholder="e.g. Looking for enterprise pricing"
                            />
                          </label>
                          <label className="flex flex-col gap-1">
                            <span className="text-[11px] text-muted-foreground">
                              Business (e.g. {"{{ business }}"})
                            </span>
                            <Input
                              value={customBusiness}
                              onChange={(e) => setCustomBusiness(e.target.value)}
                              placeholder="e.g. Acme Corp"
                            />
                          </label>
                          <label className="flex flex-col gap-1">
                            <span className="text-[11px] text-muted-foreground">
                              Source (e.g. {"{{ source }}"})
                            </span>
                            <Input
                              value={customSource}
                              onChange={(e) => setCustomSource(e.target.value)}
                              placeholder="e.g. Website lead"
                            />
                          </label>
                        </div>
                      )}
                    </div>
                  </TabsContent>

                  {/* Mode 3: No Context */}
                  <TabsContent value="none" className="pt-2">
                    <div className="rounded border border-dashed p-3 text-center text-xs text-muted-foreground">
                      Raw browser test without persona or external phone number. Tools requiring a
                      phone number will simulate or report missing contact.
                    </div>
                  </TabsContent>
                </Tabs>
              </div>

              {/* Ready info card */}
              <div className="rounded-lg border bg-muted/30 p-3 text-center">
                <Volume2 className="mx-auto mb-1.5 size-6 text-muted-foreground" />
                <p className="text-sm font-medium">Ready to talk</p>
                <p className="text-xs text-muted-foreground mt-0.5">
                  WebRTC browser audio with microphone echo cancellation, VAD, and live tool
                  dispatch.
                </p>
              </div>

              <Button onClick={startTestCall} className="w-full gap-2">
                <Mic className="size-4" /> Start Test Call
              </Button>
            </div>
          )}

          {(callState === "requesting" || callState === "connecting") && (
            <div className="flex flex-col items-center justify-center gap-3 py-10">
              <div className="relative flex size-12 items-center justify-center">
                <span className="absolute inline-flex size-full animate-ping rounded-full bg-emerald-400 opacity-50" />
                <Radio className="size-6 text-emerald-600" />
              </div>
              <p className="text-sm font-medium">Connecting WebRTC session…</p>
              <p className="text-xs text-muted-foreground">
                Initializing browser microphone and dial-in pipeline.
              </p>
              <Button
                variant="ghost"
                size="sm"
                onClick={endTestCall}
                className="mt-2 text-destructive"
              >
                Cancel
              </Button>
            </div>
          )}

          {callState === "connected" && (
            <div className="flex flex-col items-center justify-center gap-5 py-4">
              <div className="flex flex-col items-center gap-1.5">
                <div className="inline-flex items-center gap-2 rounded-full bg-emerald-500/10 px-3 py-1 text-xs font-semibold text-emerald-600 dark:text-emerald-400">
                  <span className="size-2 rounded-full bg-emerald-500 animate-pulse" />
                  Connected
                </div>
                <div className="font-mono text-3xl font-bold tracking-tight">
                  {formatTimer(duration)}
                </div>
              </div>

              {/* Context Summary Banner */}
              <div className="w-full rounded-lg border bg-muted/40 p-3 text-center text-xs space-y-1">
                <div className="font-medium text-foreground">
                  Talking as: <span className="font-semibold">{activeDisplayName}</span>
                </div>
                {activeTargetPhone && (
                  <div className="text-muted-foreground flex items-center justify-center gap-1.5">
                    <Phone className="size-3" />
                    <span>Destination: {activeTargetPhone}</span>
                    {hasWhatsApp && (
                      <Badge
                        variant="outline"
                        className="text-[10px] h-4 px-1.5 gap-1 text-emerald-600 border-emerald-300 dark:border-emerald-800"
                      >
                        <MessageSquare className="size-2.5" /> WhatsApp Active
                      </Badge>
                    )}
                  </div>
                )}
              </div>

              <div className="h-6 text-center">
                {isSpeaking ? (
                  <p className="text-sm font-medium text-emerald-600 dark:text-emerald-400 animate-pulse">
                    Agent is speaking…
                  </p>
                ) : (
                  <p className="text-sm text-muted-foreground">Listening…</p>
                )}
              </div>

              <div className="flex items-center gap-4">
                <Button
                  variant={isMuted ? "destructive" : "secondary"}
                  size="lg"
                  onClick={toggleMute}
                  className="gap-2"
                >
                  {isMuted ? <MicOff className="size-4" /> : <Mic className="size-4" />}
                  {isMuted ? "Unmute" : "Mute"}
                </Button>

                <Button
                  variant="destructive"
                  size="lg"
                  onClick={endTestCall}
                  className="gap-2"
                >
                  <PhoneOff className="size-4" /> End Call
                </Button>
              </div>
            </div>
          )}

          {callState === "ended" && (
            <div className="flex flex-col items-center justify-center gap-3 py-6 text-center">
              <div className="rounded-full bg-muted p-3 text-muted-foreground">
                <PhoneOff className="size-6" />
              </div>
              <p className="text-base font-semibold">Call Ended</p>
              <p className="text-xs text-muted-foreground">
                Call recording, transcript, and tool events are being finalized.
              </p>
              <div className="flex flex-wrap items-center justify-center gap-2 mt-2">
                {runId && (
                  <Button asChild variant="outline" size="sm">
                    <Link to={`/runs/${runId}`} onClick={() => setOpen(false)}>
                      View Run Details
                    </Link>
                  </Button>
                )}
                {activeContactId && (
                  <Button asChild variant="ghost" size="sm">
                    <Link to={`/contacts/${activeContactId}`} onClick={() => setOpen(false)}>
                      View Contact Timeline
                    </Link>
                  </Button>
                )}
              </div>
            </div>
          )}

          <DialogFooter className="sm:justify-between">
            <span className="text-[11px] text-muted-foreground">Pipecat SmallWebRTC</span>
            {callState === "ended" && (
              <Button variant="ghost" size="sm" onClick={() => setCallState("idle")}>
                Done
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
