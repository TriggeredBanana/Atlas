import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { faChevronLeft, faChevronRight, faServer, faRobot } from '@fortawesome/free-solid-svg-icons';

const SERVER_LABELS = {
    connected:    'Server tilkoblet',
    disconnected: 'Server frakoblet',
    checking:     'Sjekker server…',
};

const AI_LABELS = {
    active: 'KI-agent aktiv',
    error:  'KI-agent feil',
    idle:   'KI-agent inaktiv',
};

export function Sidebar({ items, activePanel, onSelect, collapsed, onToggleCollapse, serverStatus = 'checking', aiStatus = 'idle' }) {
    return (
        <nav className={`sidebar ${collapsed ? 'sidebar--collapsed' : ''}`}>
            <div className="sidebar-header">
                {!collapsed && <span className="sidebar-heading">Meny</span>}
                <button
                    className="sidebar-toggle"
                    onClick={onToggleCollapse}
                    aria-label={collapsed ? 'Utvid meny' : 'Skjul meny'}
                >
                    <FontAwesomeIcon icon={collapsed ? faChevronRight : faChevronLeft} />
                </button>
            </div>
            <ul className="sidebar-menu">
                {items.map((item) => (
                <li key={item.id} className="sidebar-menu-item">
                    <button
                        className={`sidebar-item ${activePanel === item.id ? 'active' : ''}`}
                        onClick={() => onSelect(item.id)}
                        title={collapsed ? item.label : undefined}
                    >
                        <FontAwesomeIcon icon={item.icon} className="sidebar-icon" />
                        {!collapsed && <span className="sidebar-label">{item.label}</span>}
                    </button>
                </li>
                ))}
            </ul>
            <div className="sidebar-status">
                <div
                    className="sidebar-status-item"
                    title={SERVER_LABELS[serverStatus] ?? SERVER_LABELS.checking}
                >
                    <FontAwesomeIcon
                        icon={faServer}
                        className={`sidebar-status-icon sidebar-status-icon--${serverStatus}`}
                    />
                    {!collapsed && (
                        <span className="sidebar-status-label">
                            {SERVER_LABELS[serverStatus] ?? SERVER_LABELS.checking}
                        </span>
                    )}
                </div>
                <div
                    className="sidebar-status-item"
                    title={AI_LABELS[aiStatus] ?? AI_LABELS.idle}
                >
                    <FontAwesomeIcon
                        icon={faRobot}
                        className={`sidebar-status-icon sidebar-status-icon--${aiStatus}`}
                    />
                    {!collapsed && (
                        <span className="sidebar-status-label">
                            {AI_LABELS[aiStatus] ?? AI_LABELS.idle}
                        </span>
                    )}
                </div>
            </div>
        </nav>
    )
}