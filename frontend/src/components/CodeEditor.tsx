import React from "react";
import Editor from "@monaco-editor/react";

type CodeEditorProps = {
  value: string;
  onChange: (value: string) => void;
  minRows?: number;
  maxRows?: number;
  placeholder?: string;
  language?: string;
};

export function CodeEditor({
  value,
  onChange,
  minRows = 14,
  maxRows = 28,
  placeholder,
  language = "json"
}: CodeEditorProps) {
  return (
    <div style={{ border: "1px solid #e5e7eb", borderRadius: 8, overflow: "hidden" }}>
      <Editor
        value={value}
        onChange={(next) => onChange(next ?? "")}
        language={language}
        height={Math.max(minRows * 20, 240)}
        options={{
          minimap: { enabled: false },
          fontSize: 13,
          lineNumbers: "on",
          scrollBeyondLastLine: false,
          automaticLayout: true,
          wordWrap: "on"
        }}
      />
      {placeholder ? (
        <div style={{ padding: "4px 8px", color: "#9ca3af", fontSize: 12 }}>{placeholder}</div>
      ) : null}
    </div>
  );
}
