"""Import-once entry point, so Windows workers receive the research patches exactly once."""
import n11t_strict

if __name__ == "__main__":
    n11t_strict.main()
