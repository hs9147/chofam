import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { isAdmin, logout } from '../lib/auth';

export default function Layout() {
  const navigate = useNavigate();
  const admin = isAdmin();

  return (
    <>
      <header className="topbar">
        <h1>PaaS 콘솔</h1>
        <nav>
          {admin && <NavLink to="/">대시보드</NavLink>}
          <NavLink to="/projects">프로젝트</NavLink>
          <NavLink to="/modules">모듈</NavLink>
          <NavLink to="/providers">LLM</NavLink>
          <NavLink to="/chat">채팅</NavLink>
          {admin && <NavLink to="/audit">감사 로그</NavLink>}
        </nav>
        <span className="mutedtext" style={{ fontSize: 12 }}>
          {admin ? 'admin' : 'member'}
        </span>
        <button
          className="secondary small"
          onClick={() => {
            logout();
            navigate('/login');
          }}
        >
          로그아웃
        </button>
      </header>
      <main>
        <Outlet />
      </main>
    </>
  );
}
