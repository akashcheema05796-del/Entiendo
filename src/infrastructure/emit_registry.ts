type EmitFn = (event: string, data: unknown) => void;

const registry = new Map<string, EmitFn>();

export const emitRegistry = {
  register(sessionId: string, fn: EmitFn) {
    registry.set(sessionId, fn);
  },
  unregister(sessionId: string) {
    registry.delete(sessionId);
  },
  emit(sessionId: string, event: string, data: unknown) {
    registry.get(sessionId)?.(event, data);
  },
};
