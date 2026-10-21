from odoo import models


class DiscussChannel(models.Model):
    _inherit = 'discuss.channel'

    def _message_post_after_hook(self, message, msg_vals):
        res = super()._message_post_after_hook(message, msg_vals)
        assistant = self.env['miro.ai.assistant']
        bot = assistant._bot_partner()
        if (bot and len(self) == 1 and message.message_type == 'comment'
                and message.author_id != bot
                # conversation privée avec le bot, ou bot mentionné (@Miro Assistant) dans un canal
                and ((self.channel_type == 'chat' and bot in self.sudo().channel_member_ids.partner_id)
                     or bot in message.partner_ids)):
            assistant._schedule_answer(self, message)
        return res
