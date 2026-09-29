export function bindBrowserPeerLifecycle(
  peer: RTCPeerConnection,
  getCurrentPeer: () => RTCPeerConnection | null,
  onConnected: () => void,
  onEnded: () => void,
  controlChannel?: RTCDataChannel,
) {
  let ended = false;

  const isCurrent = () => getCurrentPeer() === peer && !ended;

  const end = () => {
    if (!isCurrent()) return;
    ended = true;
    onEnded();
  };

  peer.onconnectionstatechange = () => {
    if (getCurrentPeer() !== peer || ended) return;

    if (peer.connectionState === "connected") {
      onConnected();
      return;
    }

    if (
      peer.connectionState === "disconnected" ||
      peer.connectionState === "failed" ||
      peer.connectionState === "closed"
    ) {
      end();
    }
  };

  const bindControlChannel = (channel: RTCDataChannel) => {
    channel.onmessage = (messageEvent) => {
      if (!isCurrent() || typeof messageEvent.data !== "string") return;
      try {
        const message = JSON.parse(messageEvent.data) as {
          type?: string;
          message?: { type?: string };
        };
        if (message.type === "signalling" && message.message?.type === "peerLeft") {
          end();
        }
      } catch {
        // Non-JSON data-channel messages are unrelated to lifecycle state.
      }
    };
  };

  if (controlChannel) bindControlChannel(controlChannel);
  peer.ondatachannel = (event) => bindControlChannel(event.channel);

  return { isCurrent };
}
