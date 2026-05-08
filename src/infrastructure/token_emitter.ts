import { EventEmitter } from 'events';

// Per-session token bus. Nodes emit here; server.ts forwards to the socket.
class TokenEmitter extends EventEmitter {}
export const tokenEmitter = new TokenEmitter();
tokenEmitter.setMaxListeners(200);
