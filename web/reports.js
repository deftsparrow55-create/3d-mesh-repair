import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

// Confined to this pack's report node. No prototype overrides or remote resources.
app.registerExtension({
    name: "AstraForge.TrustedSurface.Reports.v1",
    nodeCreated(node) {
        if (node.comfyClass !== "AstraTrustedReportV1") return;
        if (typeof node.addDOMWidget !== "function") return;
        const area = document.createElement("textarea");
        area.readOnly = true;
        area.value = "Connect a report and run the workflow. UNKNOWN means some checks are screening only.";
        Object.assign(area.style, {
            width: "100%", height: "100%", resize: "none", boxSizing: "border-box",
            color: "#dedede", background: "#20252b", font: "12px monospace",
            padding: "10px", border: "1px solid #52606b"
        });
        node.addDOMWidget("astra_report", "text", area, { serialize: false });
        node.astraReportArea = area;
        node.setSize([Math.max(node.size[0], 460), Math.max(node.size[1], 380)]);
    },
    setup() {
        api.addEventListener("executed", ({ detail }) => {
            const node = app.graph?.getNodeById(detail.display_node ?? detail.node);
            if (node?.comfyClass !== "AstraTrustedReportV1" || !node.astraReportArea) return;
            const text = detail.output?.text;
            if (Array.isArray(text)) node.astraReportArea.value = text.join("\n");
        });
    }
});
