/**
 * 设计令牌 + Naive themeOverrides。
 * 色值与 docs/05-前端界面规范.md 保持一致;组件禁止另写硬编码业务色。
 *
 * 现代蓝白玻璃系:冷灰蓝表面 + 单一蓝色强调 + 渐进模糊玻璃层。
 */

import type { GlobalThemeOverrides } from 'naive-ui'

export type ThemeMode = 'light' | 'dark'

const radiusShared = {
  '--radius-control': '9999px',
  '--radius-surface': '20px',
  '--radius-bubble': '20px',
  '--radius-input-multiline': '14px',
  '--focus-ring': '0 0 0 3px color-mix(in srgb, var(--accent) 35%, transparent)',
}

export const cssVars: Record<ThemeMode, Record<string, string>> = {
  light: {
    '--bg': '#f6f8fb',
    '--surface': '#ffffff',
    '--text': '#0f172a',
    '--text-muted': '#64748b',
    '--border': '#e2e8f0',
    '--accent': '#2563eb',
    '--danger': '#dc2626',
    '--bubble-mine': '#dbeafe',
    '--bubble-other': '#ffffff',
    '--hover': '#f1f5f9',
    '--active': '#e0e9fb',
    '--avatar-bg': '#dbeafe',
    '--avatar-fg': '#1d4ed8',
    // 玻璃与渐变装饰(新增令牌,只增不改名)
    '--surface-glass': 'color-mix(in srgb, var(--surface) 72%, transparent)',
    '--accent-soft': 'color-mix(in srgb, var(--accent) 10%, transparent)',
    '--accent-soft-hover': 'color-mix(in srgb, var(--accent) 16%, transparent)',
    '--bg-decor':
      'radial-gradient(1100px 700px at 85% -10%, rgba(37, 99, 235, 0.08), transparent 60%), ' +
      'radial-gradient(900px 600px at -10% 110%, rgba(59, 130, 246, 0.06), transparent 55%)',
    ...radiusShared,
  },
  dark: {
    '--bg': '#0f172a',
    '--surface': '#1e293b',
    '--text': '#e2e8f0',
    '--text-muted': '#94a3b8',
    '--border': '#334155',
    '--accent': '#3b82f6',
    '--danger': '#f87171',
    '--bubble-mine': '#1e40af',
    '--bubble-other': '#273449',
    '--hover': '#273449',
    '--active': '#1f3a5f',
    '--avatar-bg': '#1e3a8a',
    '--avatar-fg': '#bfdbfe',
    '--surface-glass': 'color-mix(in srgb, var(--surface) 70%, transparent)',
    '--accent-soft': 'color-mix(in srgb, var(--accent) 18%, transparent)',
    '--accent-soft-hover': 'color-mix(in srgb, var(--accent) 26%, transparent)',
    '--bg-decor':
      'radial-gradient(1100px 700px at 85% -10%, rgba(59, 130, 246, 0.14), transparent 60%), ' +
      'radial-gradient(900px 600px at -10% 110%, rgba(37, 99, 235, 0.10), transparent 55%)',
    ...radiusShared,
  },
}

function overridesFor(mode: ThemeMode): GlobalThemeOverrides {
  const v = cssVars[mode]
  const pill = v['--radius-control']
  const surface = v['--radius-surface']
  return {
    common: {
      primaryColor: v['--accent'],
      primaryColorHover: mode === 'light' ? '#1d4ed8' : '#60a5fa',
      primaryColorPressed: mode === 'light' ? '#1e40af' : '#2563eb',
      primaryColorSuppl: v['--accent'],
      errorColor: v['--danger'],
      errorColorHover: mode === 'light' ? '#b91c1c' : '#fca5a5',
      errorColorPressed: mode === 'light' ? '#991b1b' : '#ef4444',
      errorColorSuppl: v['--danger'],
      bodyColor: v['--bg'],
      cardColor: v['--surface'],
      modalColor: v['--surface'],
      popoverColor: v['--surface'],
      textColorBase: v['--text'],
      textColor1: v['--text'],
      textColor2: v['--text-muted'],
      textColor3: v['--text-muted'],
      borderColor: v['--border'],
      dividerColor: v['--border'],
      hoverColor: v['--hover'],
      borderRadius: pill,
      fontFamily: 'system-ui, "PingFang SC", "Noto Sans SC", sans-serif',
    },
    Button: {
      textColorPrimary: '#ffffff',
      borderRadiusTiny: pill,
      borderRadiusSmall: pill,
      borderRadiusMedium: pill,
      borderRadiusLarge: pill,
    },
    Card: {
      color: v['--surface'],
      borderColor: v['--border'],
      borderRadius: surface,
    },
    Input: {
      color: v['--surface'],
      border: `1px solid ${v['--border']}`,
      borderHover: `1px solid ${v['--accent']}`,
      borderFocus: `1px solid ${v['--accent']}`,
      borderRadius: pill,
      // 多行输入用较小圆角,避免胶囊拉伸难看
      textareaBorderRadius: v['--radius-input-multiline'],
    },
    Tag: {
      borderRadius: pill,
    },
    Dialog: {
      borderRadius: surface,
    },
    Drawer: {
      borderRadius: surface,
    },
  }
}

export const lightThemeOverrides = overridesFor('light')
export const darkThemeOverrides = overridesFor('dark')

/** 把 CSS 变量写到 documentElement,供 scoped 样式使用 var(--*) */
export function applyCssVars(mode: ThemeMode): void {
  const root = document.documentElement
  root.dataset.theme = mode
  const vars = cssVars[mode]
  for (const [key, value] of Object.entries(vars)) {
    root.style.setProperty(key, value)
  }
}
