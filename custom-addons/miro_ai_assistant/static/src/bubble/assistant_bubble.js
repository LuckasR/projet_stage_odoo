/** @odoo-module **/
// Bulle flottante en bas à droite : ouvre la conversation avec Miro Assistant
// dans une fenêtre de discussion Odoo (la même que dans Discuss, donc le même
// historique). Elle se décale à gauche des fenêtres de discussion ouvertes et
// disparaît tant que la fenêtre du bot est affichée, même repliée.

import { Component, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { CHAT_WINDOW_INBETWEEN_WIDTH, CHAT_WINDOW_WIDTH } from "@mail/core/common/chat_window_service";

const GAP = 20;

export class MiroAssistantBubble extends Component {
    static template = "miro_ai_assistant.Bubble";
    static props = {};

    setup() {
        this.orm = useService("orm");
        this.threadService = useService("mail.thread");
        this.store = useState(useService("mail.store"));
        this.ui = useState(useService("ui"));
        this.state = useState({ partnerId: null, opening: false });
    }

    get chatWindows() {
        return this.store.discuss.chatWindows.filter((cw) => !cw.hidden);
    }

    get botWindowOpen() {
        return this.chatWindows.some(
            (cw) => cw.thread?.type === "chat"
                && cw.thread.chatPartner?.id === this.state.partnerId
        );
    }

    get hidden() {
        // Sur téléphone, une fenêtre de discussion occupe tout l'écran
        return this.botWindowOpen || (this.ui.isSmall && this.chatWindows.length);
    }

    get style() {
        const right = this.ui.isSmall
            ? GAP
            : GAP + this.chatWindows.length * (CHAT_WINDOW_WIDTH + CHAT_WINDOW_INBETWEEN_WIDTH);
        return `right: ${right}px; bottom: ${GAP}px;`;
    }

    async onClick() {
        if (this.state.opening) {
            return;
        }
        this.state.opening = true;
        try {
            if (!this.state.partnerId) {
                this.state.partnerId = await this.orm.call("miro.ai.assistant", "get_bot_partner_id", []);
            }
            await this.threadService.openChat({ partnerId: this.state.partnerId });
        } finally {
            this.state.opening = false;
        }
    }
}

registry.category("main_components").add("miro_ai_assistant.Bubble", { Component: MiroAssistantBubble });
