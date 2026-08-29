import { useState, useEffect, useCallback, useMemo } from 'react';

const DEFAULT_CODE = {
  python: 'def solve():\n    # Write your solution here\n    pass\n\nif __name__ == "__main__":\n    solve()',
  cpp: '#include <iostream>\nusing namespace std;\n\nint main() {\n    // Write your solution here\n    return 0;\n}',
  java: 'public class Main {\n    public static void main(String[] args) {\n        // Write your solution here\n    }\n}'
};

export const useMonacoEditor = (initialLanguage = 'python') => {
  const [language, setLanguage] = useState(initialLanguage);
  const [code, setCode] = useState(DEFAULT_CODE[initialLanguage] || '');

  const defaultTemplates = useMemo(() => Object.values(DEFAULT_CODE), []);

  useEffect(() => {
    if (!code || defaultTemplates.includes(code)) {
      setCode(DEFAULT_CODE[language] || '');
    }
  }, [language, code, defaultTemplates]);

  const handleEditorWillMount = useCallback((monaco) => {
    monaco.editor.defineTheme('pitch-black', {
      base: 'vs-dark',
      inherit: true,
      rules: [],
      colors: {
        'editor.background': '#010101',
      }
    });
  }, []);

  return {
    language,
    setLanguage,
    code,
    setCode,
    handleEditorWillMount,
    defaultCode: DEFAULT_CODE,
  };
};

export default useMonacoEditor;
