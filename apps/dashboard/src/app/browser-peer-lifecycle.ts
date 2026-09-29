export function bindBrowserPeerLifecycle(
  peer: RTCPeerConnection,
  getCurrentPeer: () => RTCPeerConnection | null,
  onConnected: () => void,
  onEnded: () => void,
) {
  let ended = false;

  const isCurrent = () => getCurrentPeer() === peer && !ended;

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
      ended = true;
      onEnded();
    }
  };

  return { isCurrent };
}
