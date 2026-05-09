const toPositiveInt = (value, fallback) => {
    const parsed = Number.parseInt(value ?? '', 10)
    return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback
}

export const APP_CONFIG = {
    typewriter: {
        // 打字机正文速度（毫秒/字符），小则更快
        contentDelayMs: toPositiveInt(import.meta.env.VITE_TYPEWRITER_CONTENT_DELAY_MS, 10),
        // 思考内容速度（毫秒/字符），小则更快
        thinkingDelayMs: toPositiveInt(import.meta.env.VITE_TYPEWRITER_THINKING_DELAY_MS, 10)
    }
}
