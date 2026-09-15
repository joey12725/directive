from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("db", "0124_phase1_3_low_risk_enhancements"),
    ]

    operations = [
        migrations.AlterField(
            model_name="agent",
            name="agent_type",
            field=models.CharField(
                choices=[
                    ("openclaw", "OpenClaw"),
                    ("claude_code", "Claude Code"),
                    ("codex", "Codex"),
                    ("gemini", "Gemini"),
                    ("opencode", "OpenCode"),
                    ("acp_native", "ACP Native"),
                    ("custom", "Custom"),
                ],
                max_length=30,
            ),
        ),
    ]
