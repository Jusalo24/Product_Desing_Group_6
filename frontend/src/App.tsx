import { Link, NavLink, Route, Routes } from "react-router-dom";
import RecipeListPage from "./pages/RecipeListPage";
import RecipeDetailPage from "./pages/RecipeDetailPage";
import RecipeFormPage from "./pages/RecipeFormPage";
import MealSearchPage from "./pages/MealSearchPage";
import Logo from "./components/Logo";
import HeaderSearch from "./components/HeaderSearch";

export default function App() {
  return (
    <>
      <header className="site-header">
        <div className="site-header__inner">
          <Link to="/" className="logo" aria-label="Recipe App home">
            <Logo />
          </Link>
          <div className="site-header__right">
            <HeaderSearch />
            <nav className="main-nav" aria-label="Main navigation">
              <NavLink to="/" end>
                Home
              </NavLink>
              <NavLink to="/meals/search">Browse recipes</NavLink>
              <NavLink to="/my-recipes">My recipes</NavLink>
              <NavLink to="/new">New recipe</NavLink>
            </nav>
          </div>
        </div>
      </header>
      <div className="tagline-band">
        <span>Search it</span>
        <span className="tagline-band__script">cook it</span>
        <span>love it</span>
      </div>
      <main className="container">
        <Routes>
          <Route path="/" element={<MealSearchPage />} />
          <Route path="/meals/search" element={<MealSearchPage />} />
          <Route path="/my-recipes" element={<RecipeListPage />} />
          <Route path="/my-recipes/new" element={<RecipeFormPage />} />
          <Route path="/new" element={<RecipeFormPage />} />
          <Route path="/recipes/:id" element={<RecipeDetailPage />} />
          <Route path="*" element={<p>Page not found.</p>} />
        </Routes>
      </main>
    </>
  );
}
