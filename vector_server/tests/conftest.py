import sys
from pathlib import Path

# Ensure vector_server is on the path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import all vector modules so they register with the BaseVector registry
import vectors.agent_config  # noqa: F401
import vectors.ansi_terminal  # noqa: F401
import vectors.claude_hooks  # noqa: F401
import vectors.code_comment  # noqa: F401
import vectors.copilot_vscode  # noqa: F401
import vectors.email_injection  # noqa: F401
import vectors.gh_extension  # noqa: F401
import vectors.html  # noqa: F401
import vectors.llms_txt  # noqa: F401
import vectors.local_action  # noqa: F401
import vectors.log_injection  # noqa: F401
import vectors.markdown  # noqa: F401
import vectors.markdown_ref  # noqa: F401
import vectors.mcp_config  # noqa: F401
import vectors.mcp_schema_poison  # noqa: F401
import vectors.mcp_shadow  # noqa: F401
import vectors.multimodal  # noqa: F401
import vectors.pdf  # noqa: F401
import vectors.rag  # noqa: F401
import vectors.robots_txt  # noqa: F401
import vectors.skill_md  # noqa: F401
import vectors.unicode  # noqa: F401
import vectors.windsurf_rules  # noqa: F401
