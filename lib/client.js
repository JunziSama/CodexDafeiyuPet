// dsh-pet-indesktop settings section: creates independent desktop-pet cards
// and controls show/hide/remove without touching dsh-pet or dsh-dafeiyu.
window.__ModuleLoader__.load({
  id: 'dsh-pet-indesktop',
  factory: function (require) {
    const module = { exports: {} }
    const exports = module.exports
    const React = require('react')
    const { useEffect, useState } = React

    const ENDPOINT = '/plugins/dsh-pet-indesktop/config'
    const CARD_STYLE = {
      listStyle: 'none',
      border: '1px solid var(--border-color, #d8d8d8)',
      borderRadius: 12,
      padding: 14,
      background: 'var(--surface-color, transparent)',
      display: 'grid',
      gap: 12,
    }
    const ROW_STYLE = {
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'center',
      gap: 12,
      minHeight: 28,
    }
    const BUTTON_STYLE = {
      padding: '5px 12px',
      borderRadius: 8,
      border: '1px solid var(--border-color, #d8d8d8)',
      background: 'var(--surface-color, transparent)',
      color: 'var(--text-color, inherit)',
      cursor: 'pointer',
    }
    const TOGGLE_STYLE = { width: 16, height: 16, accentColor: 'var(--accent-color, #5e9cff)' }

    function readCards(value) {
      return Array.isArray(value?.cards) ? value.cards : []
    }

    function patch(body) {
      return fetch(ENDPOINT, {
        method: 'PATCH',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(body),
      })
    }

    function newCardId() {
      return 'card-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 6)
    }

    function Card({ card, onPatch, onRemove, disabled }) {
      const [name, setName] = useState(card.name || '独立桌宠')
      return React.createElement('li', { style: CARD_STYLE, 'data-testid': 'pet-indesktop-card' },
        React.createElement('div', { style: ROW_STYLE },
          React.createElement('input', {
            value: name,
            disabled,
            style: { flex: 1, padding: '5px 8px', borderRadius: 6, border: '1px solid var(--border-color, #d8d8d8)' },
            onChange: (e) => setName(e.target.value),
            onBlur: () => onPatch({ id: card.id, name: name.trim() || card.name }),
          }),
          React.createElement('button', { style: BUTTON_STYLE, disabled, onClick: () => onRemove(card.id) }, '移除'),
        ),
        React.createElement('label', { style: ROW_STYLE },
          React.createElement('span', null, '显示桌宠卡片'),
          React.createElement('input', {
            type: 'checkbox',
            style: TOGGLE_STYLE,
            disabled,
            checked: card.visible !== false,
            onChange: (e) => onPatch({ id: card.id, visible: e.target.checked }),
          }),
        ),
      )
    }

    function PetIndesktopSection() {
      const [state, setState] = useState({ loading: true, err: null, config: null })

      const reload = () => {
        fetch(ENDPOINT)
          .then((response) => {
            if (!response.ok) throw new Error('HTTP ' + response.status)
            return response.json()
          })
          .then((config) => setState({ loading: false, err: null, config }))
          .catch((err) => setState({ loading: false, err: '读取独立桌宠设置失败: ' + String(err && err.message || err), config: state.config }))
      }

      useEffect(() => {
        reload()
        const timer = setInterval(reload, 5000)
        return () => clearInterval(timer)
      }, [])

      const write = (body, rollbackConfig) => {
        const previous = state.config
        if (rollbackConfig) setState((s) => ({ ...s, config: rollbackConfig }))
        patch(body)
          .then((response) => {
            if (!response.ok) throw new Error('HTTP ' + response.status)
            return response.json()
          })
          .then((config) => setState((s) => ({ ...s, config, err: null })))
          .catch((err) => {
            setState((s) => ({
              ...s,
              config: previous || s.config,
              err: '写入独立桌宠设置失败: ' + String(err && err.message || err),
            }))
          })
      }

      const config = state.config
      const cards = readCards(config || {})
      const enabled = config ? config.enabled !== false : true

      const patchCard = (patchValue) => {
        const nextCards = cards.map((card) => card.id === patchValue.id ? { ...card, ...patchValue } : card)
        write({ cards: nextCards }, state.config)
      }

      const addCard = () => {
        const nextCards = [...cards, { id: newCardId(), name: '独立桌宠 ' + (cards.length + 1), visible: true }]
        write({ cards: nextCards }, state.config)
      }

      const removeCard = (cardId) => {
        const nextCards = cards.filter((card) => card.id !== cardId)
        write({ cards: nextCards }, state.config)
      }

      return React.createElement('ul', { style: { listStyle: 'none', margin: 0, padding: 0, display: 'grid', gap: 12 } },
        React.createElement('li', { style: CARD_STYLE, 'data-testid': 'pet-indesktop-section' },
          React.createElement('div', { style: ROW_STYLE },
            React.createElement('div', null,
              React.createElement('strong', { style: { fontSize: 16 } }, '独立桌宠（dsh-pet-indesktop）'),
              React.createElement('p', { style: { margin: '5px 0 0', opacity: 0.72 } },
                '基于 dsh-pet-indesktop 的透明 WebM 动画，根据 EAC 工作状态自动切换动作；与原大肥鱼插件共存。'),
            ),
            React.createElement('input', {
              type: 'checkbox',
              style: TOGGLE_STYLE,
              checked: enabled,
              onChange: (e) => write({ enabled: e.target.checked }, state.config),
            }),
          ),
          state.err ? React.createElement('div', { role: 'status', style: { fontSize: 12, color: '#e5484d' } }, state.err) : null,
        ),
        state.loading
          ? React.createElement('li', { style: CARD_STYLE }, React.createElement('span', null, '正在读取设置…'))
          : null,
        cards.map((card, index) => React.createElement(Card, {
          key: card.id,
          card,
          disabled: !enabled,
          onPatch: patchCard,
          onRemove: removeCard,
        })),
        React.createElement('li', { style: CARD_STYLE },
          React.createElement('div', { style: ROW_STYLE },
            React.createElement('span', { style: { opacity: 0.72 } }, '新增一张独立控制的桌宠卡片'),
            React.createElement('button', {
              style: BUTTON_STYLE,
              disabled: !enabled || cards.length >= 4,
              onClick: addCard,
            }, '+ 创建新卡片'),
          ),
        ),
      )
    }

    function apply(ctx) {
      ctx.slots.inject('settings.section', () => ctx.slots.register({
        name: 'settings.section',
        id: 'pet-indesktop-settings',
        order: 9,
        label: () => '独立桌宠',
      }, PetIndesktopSection))
    }

    exports.apply = apply
    exports.inject = ['slots']
    return module.exports
  },
})
